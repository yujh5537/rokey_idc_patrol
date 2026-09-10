#!/usr/bin/env python3

import os
import yaml

import rclpy
from rclpy.node import Node

from std_msgs.msg import String, Bool
from ament_index_python.packages import get_package_share_directory


class PatrolPlanner(Node):

    def __init__(self):
        super().__init__('patrol_planner')

        # ===== config 경로 =====
        package_share = get_package_share_directory('idc_mission')

        self.config_path = os.path.join(
            package_share,
            'config',
            'inspection_poses.yaml'
        )

        # ===== YAML 로드 =====
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.racks = self.config['racks']
        self.verify_config = self.config['verify']
        self.patrol_order = self.config['patrol_order']

        self.inspect_hold_sec = float(
            self.config.get('inspect_hold_sec', 3.0)
        )

        # 현재 순찰 순번
        self.current_idx = -1

        # ===== Publisher =====
        # namespace=/robot11 실행 시
        # /robot11/mission/rack_target
        self.rack_target_pub = self.create_publisher(
            String,
            'mission/rack_target',
            10
        )

        # ===== Subscriber =====
        # 다음 랙 요청
        self.next_rack_sub = self.create_subscription(
            Bool,
            'mission/next_rack',
            self.next_rack_callback,
            10
        )

        self.get_logger().info(
            f'Inspection pose config loaded: {self.config_path}'
        )

        self.get_logger().info(
            f'Rack count = {len(self.racks)}'
        )

        self.get_logger().info(
            f'Patrol order: {" -> ".join(self.patrol_order)}'
        )

    def get_normal_pose(self, rack_id):
        rack = self.racks[rack_id]
        pose = rack['normal_pose']

        return {
            'x': float(pose['x']),
            'y': float(pose['y']),
            'yaw': float(pose['yaw'])
        }

    def get_verify_pose(self, rack_id):
        rack = self.racks[rack_id]
        normal = self.get_normal_pose(rack_id)

        offset = self.verify_config.get('offset_m')
        top_yaw = self.verify_config.get('top_yaw')
        bottom_yaw = self.verify_config.get('bottom_yaw')

        if offset is None:
            raise ValueError('verify.offset_m is not set yet')

        sign = int(rack['verify_x_sign'])

        verify_x = normal['x'] + sign * float(offset)
        verify_y = normal['y']

        if normal['yaw'] > 0:
            if top_yaw is None:
                raise ValueError('verify.top_yaw is not set yet')

            verify_yaw = float(top_yaw)

        else:
            if bottom_yaw is None:
                raise ValueError('verify.bottom_yaw is not set yet')

            verify_yaw = float(bottom_yaw)

        return {
            'x': verify_x,
            'y': verify_y,
            'yaw': verify_yaw
        }

    def next_rack_callback(self, msg):
        if not msg.data:
            return

        self.current_idx += 1

        # 전체 랙 완료
        if self.current_idx >= len(self.patrol_order):
            self.get_logger().info(
                'Patrol rack sequence completed'
            )
            return

        rack_id = self.patrol_order[self.current_idx]
        normal = self.get_normal_pose(rack_id)

        out = String()
        out.data = rack_id

        self.rack_target_pub.publish(out)

        self.get_logger().info(
            f'[TARGET {self.current_idx:02d}] '
            f'{rack_id} '
            f'x={normal["x"]:.3f}, '
            f'y={normal["y"]:.3f}, '
            f'yaw={normal["yaw"]:.4f}'
        )


def main(args=None):
    rclpy.init(args=args)

    node = PatrolPlanner()

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
