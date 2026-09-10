#!/usr/bin/env python3
"""
관제 PC — 순찰 단계 bringup (Phase 2).

Phase 1(SLAM 정렬 + map_merge = control_pc_full.launch.py)을 **종료하고**, 두 로봇이
도킹된 상태에서 관제 PC 한 대에서 실행한다. robot5·robot11 각각에 대해:

  turtlebot4_navigation/localization.launch.py   map_server + AMCL (MAP-02 정적지도)
  turtlebot4_navigation/nav2.launch.py           Nav2 (robotN 전용 nav2_patrol.yaml)
  rviz2 (+ initialpose·tf 리맵)                   언도킹 후 2D Pose Estimate 용

지도는 SLAM/병합 결과가 아니라 src/idc_bringup/maps/idc_testbed.yaml (MAP-02) 를 쓴다.
순찰 스크립트(robotN_agv/*.py)가 이 규격(frame=map, 90x132, res 0.05, origin -0.5,-0.5)을
강제 검사하기 때문이다. SLAM 으로 새로 만든 맵을 쓰려면 스크립트의 map_matches() 를
먼저 완화해야 한다.

사용:
  ros2 launch amr/launch/patrol_bringup.launch.py
  ros2 launch amr/launch/patrol_bringup.launch.py rviz:=false
  ros2 launch amr/launch/patrol_bringup.launch.py map:=/abs/path/other_map.yaml

lifecycle 노드가 모두 active 되면 각 RViz 에서:
  Fixed Frame = map, Add > Map(/robotN/map, Durability=Transient Local),
  Add > LaserScan(/robotN/scan). 로봇을 언도킹한 뒤 2D Pose Estimate 로 실제 위치 지정.
이어서 amr/launch/patrol_start.launch.py 로 순찰 시작.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.actions import IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_AMR = os.path.join(_REPO, 'amr')
_TB4_NAV = get_package_share_directory('turtlebot4_navigation')

_DEFAULT_MAP = os.path.join(_REPO, 'src', 'idc_bringup', 'maps', 'idc_testbed.yaml')

# ns -> robotN 전용 Nav2 파라미터 (전진 0.15 m/s, 8cm/8deg 도착 허용; 두 파일 동일)
NAV2_PARAMS = {
    'robot5': os.path.join(_AMR, 'scripts', 'robot5_agv', 'nav2_patrol.yaml'),
    'robot11': os.path.join(_AMR, 'scripts', 'robot11_agv', 'nav2_patrol.yaml'),
}


def _robot_group(ns, map_yaml, use_rviz):
    tf, tf_static = f'/{ns}/tf', f'/{ns}/tf_static'
    return GroupAction([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(_TB4_NAV, 'launch', 'localization.launch.py')),
            launch_arguments={'namespace': f'/{ns}', 'map': map_yaml}.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(_TB4_NAV, 'launch', 'nav2.launch.py')),
            launch_arguments={'namespace': f'/{ns}',
                              'params_file': NAV2_PARAMS[ns]}.items()),
        Node(
            package='rviz2', executable='rviz2', name=f'rviz2_{ns}', output='log',
            remappings=[('/initialpose', f'/{ns}/initialpose'),
                        ('/goal_pose', f'/{ns}/goal_pose'),
                        ('/clicked_point', f'/{ns}/clicked_point'),
                        ('/tf', tf), ('/tf_static', tf_static)],
            condition=IfCondition(use_rviz)),
    ])


def generate_launch_description():
    map_yaml = LaunchConfiguration('map')
    use_rviz = LaunchConfiguration('rviz')
    return LaunchDescription([
        DeclareLaunchArgument(
            'map', default_value=_DEFAULT_MAP,
            description='map_server 정적지도 (기본 MAP-02 idc_testbed.yaml)'),
        DeclareLaunchArgument('rviz', default_value='true'),
        _robot_group('robot5', map_yaml, use_rviz),
        _robot_group('robot11', map_yaml, use_rviz),
    ])
