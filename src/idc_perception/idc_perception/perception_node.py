#!/usr/bin/env python3
"""
perception_node — 도어 박스 + 마커 + MissionState → /robotN/perception/objects (ObjectArray, 현재 랙 1건)
SDD 5.4 규칙:
 ① 화면 중앙(cx)에 가장 가까운 마커 → rack_id = "R%02d" % aruco_id
 ② 화면 중앙에 가장 가까운 도어 박스 1개만 채택
 ③ expected_rack_id 마커가 없으면 rack_id=기대값, marker_detected=false
 ④ MARKER_CHECK 중 마커가 읽히면 그 ID로 확정, marker_detected=true
 ⑤ 랙 1개당 Object 1개
배치: PC1·PC2 (--ros-args -r __ns:=/robotN)
"""
import os

import yaml
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.duration import Duration
from ament_index_python.packages import get_package_share_directory
from vision_msgs.msg import Detection2DArray
from idc_msgs.msg import ObjectArray, Object, MissionState

INSPECT_STATES = ("INSPECT", "MARKER_CHECK")


def load_racks(path: str):
    """racks.yaml → {aruco_id:int → (rack_id, zone_id)}, {rack_id → zone_id}."""
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    racks = doc.get("racks") or []
    by_aruco, zone_of = {}, {}
    for r in racks:
        aid = int(r["aruco_id"])
        rid = str(r.get("rack_id") or f"R{aid:02d}")
        zid = str(r.get("zone_id") or r.get("zone") or "")
        by_aruco[aid] = (rid, zid)
        zone_of[rid] = zid
    if len(by_aruco) == 0:
        raise RuntimeError(f"{path}: racks 항목 0개")
    return by_aruco, zone_of


class PerceptionNode(Node):
    def __init__(self):
        super().__init__("perception_node")
        ns = self.get_namespace().strip("/")                       # "robot5"
        self.declare_parameter("robot_id", ns if ns else "robot5")
        self.declare_parameter("racks_yaml", "")                    # 비우면 idc_bringup/config/racks.yaml
        self.declare_parameter("image_width", 640)                  # cx = width/2
        self.declare_parameter("sync_tol_sec", 0.15)                # 마커·도어 프레임 짝짓기 허용 오차
        self.declare_parameter("publish_without_door", True)        # 도어 0개 프레임도 발행(door_state="")

        self.robot_id = self.get_parameter("robot_id").value
        path = self.get_parameter("racks_yaml").value or os.path.join(
            get_package_share_directory("idc_bringup"), "config", "racks.yaml")
        self.by_aruco, self.zone_of = load_racks(path)
        self.cx = float(self.get_parameter("image_width").value) / 2.0
        self.sync_tol = Duration(seconds=float(self.get_parameter("sync_tol_sec").value))
        self.pub_no_door = bool(self.get_parameter("publish_without_door").value)

        self.state, self.expected = "INIT", ""
        self.last_markers = None                                    # 최신 마커 프레임
        self.stat = {"pub": 0, "no_rack": 0}

        self.create_subscription(MissionState, "mission/state", self.on_state, 10)
        self.create_subscription(Detection2DArray, "perception/markers", self.on_markers, 10)
        self.create_subscription(Detection2DArray, "perception/detections", self.on_detections, 10)
        self.pub = self.create_publisher(ObjectArray, "perception/objects", 10)
        self.create_timer(5.0, self.report)
        self.get_logger().info(
            f"perception_node up: robot={self.robot_id} racks={len(self.by_aruco)} cx={self.cx} yaml={path}")

    # ---------- 입력 ----------
    def on_state(self, m: MissionState):
        if m.state != self.state or m.expected_rack_id != self.expected:
            self.get_logger().info(f"state {self.state}→{m.state} expected={m.expected_rack_id!r}")
        self.state, self.expected = m.state, m.expected_rack_id

    def on_markers(self, m: Detection2DArray):
        self.last_markers = m

    def on_detections(self, m: Detection2DArray):
        # 도어 프레임이 "틱"이다. 같은 시각의 마커 프레임을 붙여 판정한다.
        markers = []
        if self.last_markers is not None:
            dt = abs((Time.from_msg(m.header.stamp)
                      - Time.from_msg(self.last_markers.header.stamp)).nanoseconds)
            if dt <= self.sync_tol.nanoseconds:
                markers = self.last_markers.detections
        self.process(m.header, m.detections, markers)

    # ---------- 규칙 ①~⑤ ----------
    def process(self, header, doors, markers):
        # ① 중앙에 가장 가까운 마커
        seen = {}                                                  # aruco_id → dist_to_cx
        for d in markers:
            aid = int(d.results[0].hypothesis.class_id)
            if aid in self.by_aruco:
                seen[aid] = abs(d.bbox.center.position.x - self.cx)
        center_aid = min(seen, key=seen.get) if seen else None
        expected_aid = self._aruco_of(self.expected)

        # ③ ④ rack_id · marker_detected 결정
        if self.state == "INSPECT" and self.expected:
            rack_id = self.expected
            marker_detected = expected_aid in seen
        elif self.state == "MARKER_CHECK" and self.expected:
            if center_aid is not None:                             # ④ 읽힌 ID로 확정
                rack_id, marker_detected = self.by_aruco[center_aid][0], True
            else:
                rack_id, marker_detected = self.expected, False
        else:                                                      # 창 밖: 관측만
            if center_aid is None:
                self.stat["no_rack"] += 1
                self._publish(header, [])
                return
            rack_id, marker_detected = self.by_aruco[center_aid][0], True

        # ② 중앙에 가장 가까운 도어 박스 1개
        door = min(doors, key=lambda d: abs(d.bbox.center.position.x - self.cx), default=None)
        if door is None and not self.pub_no_door:
            self._publish(header, [])
            return

        o = Object()
        o.rack_id = rack_id
        o.zone_id = self.zone_of.get(rack_id, "")
        if door is not None:
            cls = door.results[0].hypothesis.class_id            # "rack_door_open" | "rack_door_closed"
            o.door_state = "open" if cls.endswith("open") else ("closed" if cls.endswith("closed") else "")
            # door_state=="" 는 "도어 관측 실패"이므로 confidence 도 0. 도어가 아닌 클래스의 score 를
            # 흘려보내면 Event_engine 이 분모에서 제외한 프레임에 값이 남아 로그 해석을 흐린다.
            o.confidence = float(door.results[0].hypothesis.score) if o.door_state else 0.0
        else:
            o.door_state, o.confidence = "", 0.0                   # 도어 미검출 프레임 (승인 사항)
        o.marker_detected = marker_detected
        self._publish(header, [o])                                 # ⑤ 랙 1개 = Object 1개

    def _aruco_of(self, rack_id: str):
        try:
            return int(rack_id[1:]) if rack_id else None           # "R17" → 17 (racks.yaml 규칙 R%02d)
        except ValueError:
            return None

    def _publish(self, header, objs):
        msg = ObjectArray()
        msg.header = header
        msg.robot_id = self.robot_id
        msg.objects = objs
        self.pub.publish(msg)
        self.stat["pub"] += 1

    def report(self):
        self.get_logger().info(
            f"objects pub={self.stat['pub'] / 5.0:.1f}Hz no_rack={self.stat['no_rack']} "
            f"state={self.state} exp={self.expected!r}")
        self.stat = {"pub": 0, "no_rack": 0}


def main():
    rclpy.init()
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
