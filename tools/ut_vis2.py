#!/usr/bin/env python3
"""UT-VIS2 — MissionState·ObjectArray를 합성 발행해 E5 판정을 검증한다 (rosbag 없이 결정적).
실행: python3 tools/ut_vis2.py   (다른 터미널에서 event_engine 실행 중)"""
import time

import rclpy
from rclpy.node import Node
from idc_msgs.msg import ObjectArray, Object, MissionState, SecurityEvent

R = "robot5"


class UT(Node):
    def __init__(self):
        super().__init__("ut_vis2")
        self.ps = self.create_publisher(MissionState, f"/{R}/mission/state", 10)
        self.po = self.create_publisher(ObjectArray, f"/{R}/perception/objects", 10)
        self.create_subscription(SecurityEvent, "/event/events", self.on_ev, 10)
        self.events = []

    def on_ev(self, e):
        self.events.append(e)
        print(f"   <- E5 {e.rack_id} basis={e.basis} ratio={e.open_ratio:.3f} frames={e.frames} "
              f"checked={e.marker_checked} pos=({e.position.x:.2f},{e.position.y:.2f}) zone={e.zone_id}")

    def state(self, st, exp=""):
        m = MissionState(robot_id=R, state=st, zone_id="Z2", expected_rack_id=exp,
                         rack_idx=1, rack_total=14, battery=0.9, note="")
        for _ in range(3):
            self.ps.publish(m)
            self.spin(0.05)

    def frames(self, rack, n_open, n_closed, marker=True):
        for door, cnt in (("open", n_open), ("closed", n_closed)):
            for _ in range(cnt):
                o = Object(rack_id=rack, zone_id="Z2", door_state=door,
                           confidence=0.9, marker_detected=marker)
                self.po.publish(ObjectArray(robot_id=R, objects=[o]))
                self.spin(0.01)

    def spin(self, s):
        end = time.time() + s
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.005)

    def case(self, title, fn, expect):
        print(f"\n== {title}  (기대: {expect})")
        before = len(self.events)
        fn()
        self.spin(0.4)
        got = self.events[before:]
        print(f"   결과: {len(got)}건" + ("" if got else " - 미확정"))
        return got


def main():
    rclpy.init()
    u = UT()
    u.spin(1.0)
    u.state("UNDOCK")                                    # 회차 시작

    u.case("(1) open 12 / closed 3 (ratio 0.80)", lambda: (
        u.state("INSPECT", "R17"), u.frames("R17", 12, 3), u.state("RESUME")), "E5 basis=yolo")

    u.case("(2) 경계 - open 9 / closed 0 (프레임 미달)", lambda: (
        u.state("INSPECT", "R18"), u.frames("R18", 9, 0), u.state("RESUME")), "미확정")

    u.case("(3) 경계 - open 10 / closed 7 (ratio 0.588)", lambda: (
        u.state("INSPECT", "R19"), u.frames("R19", 10, 7), u.state("RESUME")), "미확정")

    u.case("(4) 경계 - open 10 / closed 6 (ratio 0.625)", lambda: (
        u.state("INSPECT", "R20"), u.frames("R20", 10, 6), u.state("RESUME")), "E5 basis=yolo")

    u.case("(5) marker_missing - closed 15, 마커 없음", lambda: (
        u.state("INSPECT", "R21"), u.frames("R21", 0, 15, marker=False), u.state("RESUME")),
        "E5 basis=marker_missing")

    u.case("(6) MARKER_CHECK 후 확정", lambda: (
        u.state("INSPECT", "R22"), u.frames("R22", 0, 12, marker=False),
        u.state("MARKER_CHECK", "R22"), u.frames("R22", 0, 4, marker=True), u.state("RESUME")),
        "E5 marker_missing, marker_checked=true")

    u.case("(7) 정상 랙 - closed 20, 마커 있음", lambda: (
        u.state("INSPECT", "R23"), u.frames("R23", 0, 20), u.state("RESUME")), "미확정(오탐 0)")

    u.case("(8) 중복 - R17 재응시", lambda: (
        u.state("INSPECT", "R17"), u.frames("R17", 14, 1), u.state("RESUME")), "미발행(dedup)")

    u.case("(9) 새 회차 후 R17", lambda: (
        u.state("DOCK"), u.state("INIT"), u.state("UNDOCK"),
        u.state("INSPECT", "R17"), u.frames("R17", 14, 1), u.state("RESUME")), "E5 재발행")

    print(f"\n총 E5 {len(u.events)}건 — 기대 5건 (1,4,5,6,9), 오탐 0, 중복 0")
    u.destroy_node()
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
