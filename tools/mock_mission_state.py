#!/usr/bin/env python3
"""MIS-01 대체 mock — mission/state 를 2Hz로 발행. 표준입력 명령:
   i R17  → INSPECT expected=R17 | m → MARKER_CHECK | r → RESUME | n → NAVIGATE | q → 종료
실행: python3 tools/mock_mission_state.py --ros-args -r __ns:=/robot5"""
import sys
import threading

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from idc_msgs.msg import MissionState


class Mock(Node):
    def __init__(self):
        super().__init__("mock_mission_state")
        ns = self.get_namespace().strip("/") or "robot5"
        self.m = MissionState(robot_id=ns, state="NAVIGATE", zone_id="Z1", expected_rack_id="",
                              rack_idx=0, rack_total=14, battery=0.9, note="mock")
        self.pub = self.create_publisher(MissionState, "mission/state", 10)
        self.create_timer(0.5, lambda: self.pub.publish(self.m))
        threading.Thread(target=self.reader, daemon=True).start()
        print("명령: i R17 / m / r / n / q", flush=True)

    def reader(self):
        for line in sys.stdin:
            t = line.split()
            if not t:
                continue
            c = t[0].lower()
            if c == "i" and len(t) > 1:
                self.m.state, self.m.expected_rack_id = "INSPECT", t[1].upper()
            elif c == "m":
                self.m.state = "MARKER_CHECK"
            elif c == "r":
                self.m.state, self.m.expected_rack_id = "RESUME", ""
            elif c == "n":
                self.m.state, self.m.expected_rack_id = "NAVIGATE", ""
            elif c == "q":
                rclpy.try_shutdown()
                return
            print(f"→ {self.m.state} expected={self.m.expected_rack_id!r}", flush=True)


def main():
    rclpy.init()
    n = Mock()
    try:
        rclpy.spin(n)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass                       # q 명령·SIGTERM 은 정상 종료 경로
    finally:
        n.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
