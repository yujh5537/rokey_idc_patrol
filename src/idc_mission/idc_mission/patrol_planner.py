#!/usr/bin/env python3

import os
import yaml

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, String
from ament_index_python.packages import get_package_share_directory


class PatrolPlanner(Node):

    def __init__(self):
        super().__init__('patrol_planner')

        # ============================================================
        # Parameters
        # ============================================================

        self.declare_parameter('robot_id', 'robot11')

        self.robot_id = (
            self.get_parameter('robot_id')
            .get_parameter_value()
            .string_value
        )

        # ============================================================
        # Config
        #
        # 좌표/구역/순찰 정본:
        #   idc_bringup/config/racks.yaml
        #
        # Mission 동작 설정:
        #   idc_mission/config/inspection_settings.yaml
        # ============================================================

        bringup_share = get_package_share_directory('idc_bringup')
        mission_share = get_package_share_directory('idc_mission')

        self.racks_config_path = os.path.join(
            bringup_share,
            'config',
            'racks.yaml'
        )

        self.settings_path = os.path.join(
            mission_share,
            'config',
            'inspection_settings.yaml'
        )

        # ============================================================
        # Load racks.yaml
        # ============================================================

        with open(self.racks_config_path, 'r') as f:
            self.racks_config = yaml.safe_load(f)

        self.racks = {
            rack['rack_id']: rack
            for rack in self.racks_config['racks']
        }

        # ============================================================
        # Load inspection settings
        # ============================================================

        with open(self.settings_path, 'r') as f:
            self.settings = yaml.safe_load(f)

        self.inspect_hold_sec = float(
            self.settings.get('inspect_hold_sec', 3.0)
        )

        self.marker_check_config = self.settings['marker_check']

        # ============================================================
        # Robot assignment
        # ============================================================

        robot_zones = self.racks_config['robot_zones']
        patrol_routes = self.racks_config['patrol_routes']

        if self.robot_id not in robot_zones:
            raise ValueError(
                f'robot_id not found in robot_zones: {self.robot_id}'
            )

        if self.robot_id not in patrol_routes:
            raise ValueError(
                f'robot_id not found in patrol_routes: {self.robot_id}'
            )

        self.assigned_zones = list(
            robot_zones[self.robot_id]
        )

        self.patrol_order = list(
            patrol_routes[self.robot_id]
        )

        self.validate_route()

        self.current_idx = -1

        # ============================================================
        # ROS
        # ============================================================

        self.rack_target_pub = self.create_publisher(
            String,
            'mission/rack_target',
            10
        )

        self.next_rack_sub = self.create_subscription(
            Bool,
            'mission/next_rack',
            self.next_rack_callback,
            10
        )

        # ============================================================
        # Startup log
        # ============================================================

        self.get_logger().info(
            f'PatrolPlanner started - robot_id={self.robot_id}'
        )

        self.get_logger().info(
            f'assigned zones={self.assigned_zones}'
        )

        self.get_logger().info(
            f'route rack count={len(self.patrol_order)}'
        )

        self.get_logger().info(
            'patrol order: '
            + ' -> '.join(self.patrol_order)
        )

    # ================================================================
    # Validation
    # ================================================================

    def validate_route(self):

        seen = set()

        for rack_id in self.patrol_order:

            if rack_id in seen:
                raise ValueError(
                    f'Duplicate rack in patrol route: {rack_id}'
                )

            seen.add(rack_id)

            if rack_id not in self.racks:
                raise ValueError(
                    f'Rack not found: {rack_id}'
                )

            zone_id = self.racks[rack_id]['zone_id']

            if zone_id not in self.assigned_zones:
                raise ValueError(
                    f'{rack_id} belongs to {zone_id}, '
                    f'but {self.robot_id} zones are '
                    f'{self.assigned_zones}'
                )

    # ================================================================
    # Rack
    # ================================================================

    def get_rack(self, rack_id):

        if rack_id not in self.racks:
            raise KeyError(
                f'Unknown rack_id: {rack_id}'
            )

        return self.racks[rack_id]

    # ================================================================
    # Normal inspection pose
    #
    # racks.yaml의 inspect_pose를 그대로 사용한다.
    # ================================================================

    def get_normal_pose(self, rack_id):

        rack = self.get_rack(rack_id)
        pose = rack['inspect_pose']

        return {
            'x': float(pose['x']),
            'y': float(pose['y']),
            'yaw': float(pose['yaw']),
            'zone_id': rack['zone_id'],
            'oblique': bool(rack.get('oblique', False)),
        }

    # ================================================================
    # Marker check pose
    #
    # 문 열림 / marker missing 등의 재확인용.
    # 현재 offset/yaw는 임시값.
    # ================================================================

    def get_marker_check_pose(self, rack_id):

        normal = self.get_normal_pose(rack_id)

        # 벽쪽 oblique rack은 일반 marker_check offset을 적용하지 않는다.
        # NAV-08 실측값 확정 후 별도 pose를 정의한다.
        if normal['oblique']:
            raise ValueError(
                f'{rack_id}: oblique rack marker check pose is not approved yet'
            )

        offset = float(
            self.marker_check_config['offset_m']
        )

        if normal['yaw'] >= 0.0:

            sign = int(
                self.marker_check_config[
                    'positive_yaw_x_sign'
                ]
            )

            marker_check_yaw = float(
                self.marker_check_config[
                    'positive_yaw'
                ]
            )

        else:

            sign = int(
                self.marker_check_config[
                    'negative_yaw_x_sign'
                ]
            )

            marker_check_yaw = float(
                self.marker_check_config[
                    'negative_yaw'
                ]
            )

        return {
            'x': normal['x'] + sign * offset,
            'y': normal['y'],
            'yaw': marker_check_yaw,
            'zone_id': normal['zone_id'],
        }

    # ================================================================
    # Next rack
    # ================================================================

    def next_rack_callback(self, msg):

        if not msg.data:
            return

        self.current_idx += 1

        if self.current_idx >= len(self.patrol_order):

            self.get_logger().info(
                f'Patrol completed - '
                f'{len(self.patrol_order)} racks'
            )

            return

        rack_id = self.patrol_order[
            self.current_idx
        ]

        normal = self.get_normal_pose(
            rack_id
        )

        out = String()
        out.data = rack_id

        self.rack_target_pub.publish(out)

        self.get_logger().info(
            f'[TARGET {self.current_idx + 1:02d}/'
            f'{len(self.patrol_order):02d}] '
            f'{rack_id} '
            f'zone={normal["zone_id"]} '
            f'x={normal["x"]:.3f} '
            f'y={normal["y"]:.3f} '
            f'yaw={normal["yaw"]:.4f} '
            f'oblique={normal["oblique"]}'
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
