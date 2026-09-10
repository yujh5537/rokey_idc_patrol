#!/usr/bin/env python3
"""
event_engine — 응시 창 다수결로 E5 확정 (SDD 5.5, EVT-01)
배치: PC3. 영상 미구독. 로봇 2대분 창을 각각 관리.
Inputs : /robotN/perception/objects (ObjectArray), /robotN/mission/state (MissionState), event_rules.yaml
Output : /event/events (SecurityEvent) — 이벤트당 1회
※ SDD 부록 A의 패키지명 Event_engine 대신 레포 실물 idc_event 를 사용 (REP-01 골격 기준)
"""
import os

import yaml
import rclpy
from rclpy.node import Node
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Point
from idc_msgs.msg import ObjectArray, MissionState, SecurityEvent

WINDOW_STATES = ("INSPECT", "MARKER_CHECK")   # 창이 열려 있는 상태
RUN_RESET_STATES = ("INIT", "UNDOCK")          # 새 순찰 회차 시작 → dedup 초기화


def load_racks(path):
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    out = {}
    for r in (doc.get("racks") or []):
        rid = str(r.get("rack_id") or f"R{int(r['aruco_id']):02d}")
        out[rid] = (float(r["x"]), float(r["y"]), str(r.get("zone_id") or r.get("zone") or ""))
    if not out:
        raise RuntimeError(f"{path}: racks 0개")
    return out


class Window:
    """한 로봇의 응시 창. INSPECT에서 열리고 창 밖 상태로 나갈 때 판정한다."""

    def __init__(self, expect):
        self.expect = expect            # 기대 rack_id
        self.inspect = []               # INSPECT 구간 Object (marker_missing 판정 대상)
        self.all = []                   # INSPECT + MARKER_CHECK 전체 (open 다수결 대상)
        self.marker_checked = False


class EventEngine(Node):
    def __init__(self):
        super().__init__("event_engine")
        self.declare_parameter("robots", ["robot5", "robot11"])
        self.declare_parameter("rules_yaml", "")
        self.declare_parameter("racks_yaml", "")
        self.declare_parameter("objects_timeout_sec", 5.0)   # SDD 7장 인식 노드 다운 감지

        rules_path = self.get_parameter("rules_yaml").value or os.path.join(
            get_package_share_directory("idc_event"), "config", "event_rules.yaml")
        racks_path = self.get_parameter("racks_yaml").value or os.path.join(
            get_package_share_directory("idc_bringup"), "config", "racks.yaml")
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        e5 = rules["E5"]
        self.open_class = e5["class"]                          # rack_door_open
        self.min_open = int(e5["min_open_frames"])             # 10
        self.min_ratio = float(e5["open_ratio"])               # 0.6
        self.marker_is_open = bool(e5["marker_missing_is_open"])
        self.dedup_scope = str(rules.get("dedup", "per_run"))
        self.racks = load_racks(racks_path)
        self.timeout = float(self.get_parameter("objects_timeout_sec").value)

        self.robots = list(self.get_parameter("robots").value)
        self.win = {r: None for r in self.robots}      # 열린 창
        self.state = {r: "INIT" for r in self.robots}
        self.fired = {r: set() for r in self.robots}   # dedup: per_run 발행 이력
        self.last_obj = {r: None for r in self.robots}
        self.degraded = {r: False for r in self.robots}

        self.pub = self.create_publisher(SecurityEvent, "/event/events", 10)
        for r in self.robots:
            self.create_subscription(MissionState, f"/{r}/mission/state",
                                     lambda m, rb=r: self.on_state(rb, m), 10)
            self.create_subscription(ObjectArray, f"/{r}/perception/objects",
                                     lambda m, rb=r: self.on_objects(rb, m), 10)
        self.create_timer(1.0, self.watchdog)
        self.get_logger().info(
            f"event_engine up: robots={self.robots} min_open_frames={self.min_open} "
            f"open_ratio={self.min_ratio} marker_missing_is_open={self.marker_is_open} "
            f"dedup={self.dedup_scope} racks={len(self.racks)}")

    # ---------- 창 제어 (SDD 5.5) ----------
    def on_state(self, robot, m: MissionState):
        prev, cur = self.state[robot], m.state
        self.state[robot] = cur
        if cur in RUN_RESET_STATES and prev not in RUN_RESET_STATES:
            self.fired[robot].clear()                       # 새 회차 → dedup 리셋
            self.get_logger().info(f"[{robot}] 새 순찰 회차 — dedup 초기화")

        if cur == "INSPECT":
            if self.win[robot] is None or self.win[robot].expect != m.expected_rack_id:
                self.win[robot] = Window(m.expected_rack_id)  # 창 열기
                self.get_logger().info(f"[{robot}] 창 열림 expect={m.expected_rack_id}")
        elif cur == "MARKER_CHECK":
            if self.win[robot] is not None:
                self.win[robot].marker_checked = True         # 창 유지, 계속 누적
        else:
            if self.win[robot] is not None:                   # 창 닫힘 → 판정 1회
                self.judge(robot, self.win[robot])
                self.win[robot] = None

    def on_objects(self, robot, msg: ObjectArray):
        self.last_obj[robot] = self.get_clock().now()
        if self.degraded[robot]:
            self.degraded[robot] = False
            self.get_logger().info(f"[{robot}] objects 수신 복구")
        w = self.win[robot]
        if w is None or not msg.objects:
            return
        o = msg.objects[0]                                    # 현재 랙 1건
        w.all.append(o)
        if self.state[robot] == "INSPECT":
            w.inspect.append(o)

    # ---------- 판정 (SDD 5.5 의사코드) ----------
    def judge(self, robot, w: Window):
        door = [o for o in w.all if o.door_state in ("open", "closed")]   # 도어 관측 프레임만
        n = len(door)
        open_frames = sum(1 for o in door if o.door_state == "open")
        ratio = (open_frames / n) if n else 0.0
        open_by_yolo = (open_frames >= self.min_open) and (ratio >= self.min_ratio)  # 둘 다 만족

        marker_missing = self.marker_is_open and bool(w.inspect) and \
            not any(o.marker_detected for o in w.inspect)     # INSPECT 내내 마커 없음

        # MARKER_CHECK에서 읽힌 ID 우선 → 없으면 기대값
        confirmed = [o.rack_id for o in w.all if o.marker_detected]
        rack_id = confirmed[-1] if confirmed else w.expect

        self.get_logger().info(
            f"[{robot}] 판정 rack={rack_id} frames={n} open={open_frames} ratio={ratio:.2f} "
            f"yolo={open_by_yolo} marker_missing={marker_missing} checked={w.marker_checked}")

        if not (open_by_yolo or marker_missing):
            return
        if not rack_id:
            self.get_logger().warn(f"[{robot}] rack_id 없음 — E5 보류")
            return
        if rack_id in self.fired[robot]:                      # dedup: per_run
            self.get_logger().info(f"[{robot}] {rack_id} 이미 발행됨 — 중복 억제")
            return

        x, y, zone = self.racks.get(rack_id, (0.0, 0.0, ""))
        ev = SecurityEvent()
        ev.header.stamp = self.get_clock().now().to_msg()
        ev.header.frame_id = "map"
        ev.type = "E5"
        ev.robot_id = robot
        ev.zone_id = zone
        ev.rack_id = rack_id
        ev.position = Point(x=x, y=y, z=0.0)
        ev.basis = "yolo" if open_by_yolo else "marker_missing"
        ev.open_ratio = float(ratio)
        ev.frames = int(n)
        ev.marker_checked = bool(w.marker_checked)
        self.pub.publish(ev)
        self.fired[robot].add(rack_id)
        self.get_logger().warn(
            f"E5 발행 {robot} {rack_id} basis={ev.basis} ratio={ratio:.2f} frames={n}")

    # ---------- SDD 7장: 인식 노드 다운 ----------
    def watchdog(self):
        now = self.get_clock().now()
        for r in self.robots:
            t = self.last_obj[r]
            if t is None:
                continue
            if (now - t).nanoseconds * 1e-9 > self.timeout and not self.degraded[r]:
                self.degraded[r] = True
                self.get_logger().error(f"[{r}] DEGRADED — objects {self.timeout}s 미수신 (순찰은 계속)")


def main():
    rclpy.init()
    node = EventEngine()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
