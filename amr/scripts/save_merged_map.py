#!/usr/bin/env python3
"""
save_merged_map.py

map_merge 로 병합된 지도(/map)를, 두 로봇이 언도킹해서 주행을 마치고
다시 도킹을 완료했을 때 'merged_map' 이름으로 자동 저장한다.

동작:
  1. /robot5/dock_status, /robot11/dock_status 구독
  2. 두 로봇 모두 한 번 언도킹된 것을 확인 (= 매핑 주행 시작)
  3. 그 뒤 두 로봇 모두 다시 도킹되면 nav2 map_saver_cli 로 /map 저장
  4. 저장 후 종료

사용법:
  python3 save_merged_map.py
  python3 save_merged_map.py --output-dir ~/maps --name merged_map --map-topic /map
  python3 save_merged_map.py --robots robot5 robot11
"""

import argparse
import os
import subprocess

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from irobot_create_msgs.msg import DockStatus


class MergedMapSaver(Node):
    def __init__(self, robots, output_dir, name, map_topic, save_timeout):
        super().__init__('merged_map_saver')
        self.output_dir = os.path.expanduser(output_dir)
        self.name = name
        self.map_topic = map_topic
        self.save_timeout = save_timeout

        self.docked = {r: None for r in robots}       # 최신 is_docked 값
        self.undocked_seen = {r: False for r in robots}  # 언도킹을 한 번이라도 봤는지
        self.saved = False

        # create3 dock_status 는 best-effort 로 발행됨
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        for r in robots:
            self.create_subscription(
                DockStatus, f'/{r}/dock_status',
                lambda msg, ns=r: self._on_dock(ns, msg), qos)

        self.get_logger().info(
            f'도킹 상태 감시 시작 — {list(robots)} 언도킹 후 전원 재도킹 시 '
            f'"{self.name}" 저장 (dir: {self.output_dir})')

    def _on_dock(self, ns, msg):
        self.docked[ns] = msg.is_docked
        if not msg.is_docked and not self.undocked_seen[ns]:
            self.undocked_seen[ns] = True
            self.get_logger().info(f'{ns} 언도킹 감지 — 매핑 주행 시작으로 간주')
        self._maybe_save()

    def _maybe_save(self):
        if self.saved:
            return
        if not all(self.undocked_seen.values()):
            return
        if not all(v is True for v in self.docked.values()):
            return
        self.saved = True
        self._save_map()
        # 저장 끝났으면 스스로 종료
        rclpy.shutdown()

    def _save_map(self):
        os.makedirs(self.output_dir, exist_ok=True)
        stem = os.path.join(self.output_dir, self.name)
        self.get_logger().info(
            f'두 로봇 재도킹 완료 — 지도 저장 시작: {stem}.pgm / {stem}.yaml')
        cmd = [
            'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
            '-t', self.map_topic,        # -r map:=... 나 -r __ns:=... 는 안 먹음 (troubleshooting_log #6)
            '-f', stem,
            '--ros-args',
            '-p', f'save_map_timeout:={self.save_timeout}',
            '-p', 'map_subscribe_transient_local:=true',
        ]
        try:
            subprocess.run(cmd, check=True, timeout=self.save_timeout + 15.0)
            self.get_logger().info(f'지도 저장 완료: {stem}.pgm / {stem}.yaml')
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.get_logger().error(f'지도 저장 실패: {e}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--robots', nargs='+', default=['robot5', 'robot11'],
                        help='감시할 로봇 네임스페이스, 기본 robot5 robot11')
    parser.add_argument('--output-dir', default='amr/maps',
                        help='저장 디렉터리, 기본 amr/maps')
    parser.add_argument('--name', default='merged_map',
                        help='저장 파일 이름(확장자 제외), 기본 merged_map')
    parser.add_argument('--map-topic', default='/map',
                        help='병합 지도 토픽, 기본 /map')
    parser.add_argument('--save-timeout', type=float, default=20.0,
                        help='map_saver 저장 대기 시간(초), 기본 20')
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = MergedMapSaver(args.robots, args.output_dir, args.name,
                          args.map_topic, args.save_timeout)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
