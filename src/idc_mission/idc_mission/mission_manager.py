#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from std_msgs.msg import String
from idc_msgs.msg import MissionState


class MissionManager(Node):

    def __init__(self):
        super().__init__('mission_manager')

        # ===== Parameters =====
        self.declare_parameter('robot_id', 'robot11')
        self.declare_parameter('waypoint_total', 28)
        self.declare_parameter('battery', 1.0)

        self.robot_id = (
            self.get_parameter('robot_id')
            .get_parameter_value()
            .string_value
        )

        self.waypoint_total = (
            self.get_parameter('waypoint_total')
            .get_parameter_value()
            .integer_value
        )

        self.battery = (
            self.get_parameter('battery')
            .get_parameter_value()
            .double_value
        )

        # ===== Current Mission State =====
        self.state = 'PATROL'
        self.waypoint_idx = 0
        self.note = ''

        # ===== MissionState Publisher =====
        # namespace=/robot11 로 실행하면
        # /robot11/mission/state 가 됨
        self.state_pub = self.create_publisher(
            MissionState,
            'mission/state',
            10
        )

        # ===== 임시 테스트 명령 Subscriber =====
        # PATROL / INSPECT / RESUME 등을 외부에서 입력
        self.test_state_sub = self.create_subscription(
            String,
            'mission/test_state',
            self.test_state_callback,
            10
        )

        # MissionState @2Hz
        self.publish_timer = self.create_timer(
            0.5,
            self.publish_state
        )

        self.inspect_timer = None

        self.get_logger().info(
            f'Mission Manager Started - robot_id={self.robot_id}'
        )

    def publish_state(self):
        msg = MissionState()

        msg.robot_id = self.robot_id
        msg.state = self.state
        msg.waypoint_idx = self.waypoint_idx
        msg.waypoint_total = self.waypoint_total
        msg.battery = float(self.battery)
        msg.note = self.note

        self.state_pub.publish(msg)

    def transition(self, new_state, note=''):
        old_state = self.state
        self.state = new_state
        self.note = note

        self.get_logger().info(
            f'[STATE] {old_state} -> {new_state}'
        )

        self.publish_state()

    def test_state_callback(self, msg):
        command = msg.data.strip().upper()

        if command == 'INSPECT':
            self.transition(
                'INSPECT',
                'INSPECT_WINDOW_START'
            )

            # 기존 timer가 있으면 제거
            if self.inspect_timer is not None:
                self.inspect_timer.cancel()
                self.destroy_timer(self.inspect_timer)

            # 3초 후 RESUME
            self.inspect_timer = self.create_timer(
                3.0,
                self.finish_inspect
            )

        elif command == 'PATROL':
            self.transition('PATROL')

        elif command == 'RESUME':
            self.transition('RESUME')

        elif command == 'FACE':
            self.transition('FACE')

        else:
            self.get_logger().warning(
                f'Unknown test state: {command}'
            )

    def finish_inspect(self):
        if self.inspect_timer is not None:
            self.inspect_timer.cancel()
            self.destroy_timer(self.inspect_timer)
            self.inspect_timer = None

        self.transition(
            'RESUME',
            'INSPECT_WINDOW_END'
        )


def main(args=None):
    rclpy.init(args=args)

    node = MissionManager()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
