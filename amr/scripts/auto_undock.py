#!/usr/bin/env python3
"""
auto_undock.py

/robot5/map, /robot11/map 토픽이 실제로 나오기 시작할 때까지 기다린 뒤,
두 로봇을 동시에 언도킹한다.

사용법:
  python3 auto_undock.py
  python3 auto_undock.py --timeout 60
"""

import argparse
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from irobot_create_msgs.action import Undock


class AutoUndock(Node):
    def __init__(self, timeout_sec):
        super().__init__('auto_undock')
        self.timeout_sec = timeout_sec
        self.robots = ['robot5', 'robot11']

    def wait_for_map_topic(self, robot_ns):
        """해당 로봇의 map 토픽이 생길 때까지 대기. 성공 시 True, 타임아웃 시 False."""
        target = f'/{robot_ns}/map'
        self.get_logger().info(f'{target} 토픽 대기 중...')
        start = time.time()
        while time.time() - start < self.timeout_sec:
            topics = dict(self.get_topic_names_and_types())
            if target in topics:
                self.get_logger().info(f'{target} 확인됨')
                return True
            rclpy.spin_once(self, timeout_sec=1.0)
        self.get_logger().warn(f'{target} 대기 시간 초과 ({self.timeout_sec}초)')
        return False

    def undock(self, robot_ns):
        """해당 로봇을 언도킹. 완료될 때까지 대기."""
        client = ActionClient(self, Undock, f'/{robot_ns}/undock')

        self.get_logger().info(f'{robot_ns} 언도킹 액션 서버 대기 중...')
        if not client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error(f'{robot_ns} 언도킹 액션 서버를 찾을 수 없습니다.')
            return False

        self.get_logger().info(f'{robot_ns} 언도킹 시작')
        goal_msg = Undock.Goal()
        future = client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, future)

        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().error(f'{robot_ns} 언도킹 목표가 거부되었습니다.')
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        self.get_logger().info(f'{robot_ns} 언도킹 완료')
        return True

    def run(self):
        # 1. 두 로봇의 map 토픽이 나올 때까지 대기 (SLAM 준비 확인)
        ready = []
        for ns in self.robots:
            if self.wait_for_map_topic(ns):
                ready.append(ns)

        if not ready:
            self.get_logger().error('지도 토픽이 하나도 확인되지 않아 언도킹을 중단합니다.')
            return

        if len(ready) < len(self.robots):
            missing = set(self.robots) - set(ready)
            self.get_logger().warn(
                f'다음 로봇은 지도가 준비되지 않아 언도킹에서 제외합니다: {missing}')

        # 2. 준비된 로봇만 언도킹
        for ns in ready:
            self.undock(ns)

        self.get_logger().info('자동 언도킹 절차가 끝났습니다.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=float, default=60.0,
                         help='map 토픽 대기 최대 시간(초), 기본 60')
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = AutoUndock(timeout_sec=args.timeout)
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
