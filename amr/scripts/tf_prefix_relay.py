#!/usr/bin/env python3
"""
tf_prefix_relay.py

네임스페이스로 띄운 TurtleBot4 베이스/SLAM 은 토픽에는 네임스페이스가 붙지만
(/robot5/scan, /robot5/tf ...) TF 프레임 이름에는 접두사가 안 붙는다
(odom, base_link, rplidar_link, map ...). slam_toolbox 설정(slam.yaml)에
프레임 이름이 고정 문자열로 박혀 있고, turtlebot4 slam.launch.py 도 이 값을
치환하지 않기 때문이다.

두 로봇이 같은 프레임 이름을 쓰면 관제 PC 전역 TF 트리에서 서로 구분이 안 되므로,
이 노드가 로봇별 /<ns>/tf, /<ns>/tf_static 을 구독해 모든 프레임에 "<ns>/"
접두사를 붙여 전역 /tf, /tf_static 으로 재발행한다.

robot_slam.launch.py 안에서 로봇 SLAM 과 한 묶음으로 (respawn=true) 실행되므로
따로 켤 필요가 없다.

사용법:
  python3 tf_prefix_relay.py --ns robot5
  python3 tf_prefix_relay.py --ns robot5 --scan-out scan_ns --lidar-link rplidar_link
"""

import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import LaserScan

STATIC_QOS = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)


class TfPrefixRelay(Node):
    def __init__(self, ns, scan_in, scan_out, lidar_link):
        super().__init__(f'tf_prefix_relay_{ns}')
        self.prefix = ns + '/'

        self.pub_tf = self.create_publisher(TFMessage, '/tf', 100)
        self.pub_tf_static = self.create_publisher(TFMessage, '/tf_static', STATIC_QOS)
        self.create_subscription(
            TFMessage, f'/{ns}/tf',
            lambda m: self.pub_tf.publish(self._prefix_tf(m)), 100)
        self.create_subscription(
            TFMessage, f'/{ns}/tf_static',
            lambda m: self.pub_tf_static.publish(self._prefix_tf(m)), STATIC_QOS)

        self.get_logger().info(
            f'TF 접두사 중계: /{ns}/tf(_static) -> /tf(_static)  ["{self.prefix}" 접두]')

        if scan_out:
            self.expected_link = self.prefix + lidar_link
            self.pub_scan = self.create_publisher(LaserScan, f'/{ns}/{scan_out}', 10)
            self.create_subscription(LaserScan, f'/{ns}/{scan_in}', self._on_scan, 10)
            self.get_logger().info(
                f'스캔 frame_id 보정: /{ns}/{scan_in} -> /{ns}/{scan_out} '
                f'(frame_id -> {self.expected_link})')

    def _prefix_tf(self, msg):
        for t in msg.transforms:
            if not t.header.frame_id.startswith(self.prefix):
                t.header.frame_id = self.prefix + t.header.frame_id.lstrip('/')
            if not t.child_frame_id.startswith(self.prefix):
                t.child_frame_id = self.prefix + t.child_frame_id.lstrip('/')
        return msg

    def _on_scan(self, msg):
        fid = msg.header.frame_id.lstrip('/')
        msg.header.frame_id = fid if fid.startswith(self.prefix) else self.prefix + fid
        self.pub_scan.publish(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ns', required=True, help='로봇 네임스페이스 (예: robot5)')
    parser.add_argument('--scan-in', default='scan',
                        help='원본 스캔 토픽 (네임스페이스 뒤), 기본 scan')
    parser.add_argument('--scan-out', default='',
                        help='frame_id 보정한 스캔을 낼 토픽 (네임스페이스 뒤). 비우면 스캔 중계 안 함')
    parser.add_argument('--lidar-link', default='rplidar_link',
                        help='라이다 링크 이름, 기본 rplidar_link')
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = TfPrefixRelay(args.ns, args.scan_in, args.scan_out, args.lidar_link)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
