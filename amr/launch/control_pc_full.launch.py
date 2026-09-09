#!/usr/bin/env python3
"""
관제 PC 자동 실행 — SLAM + TF 정렬 + map_merge + rviz (+선택 자동 언도킹)

사용법:
  ros2 launch amr/launch/control_pc_full.launch.py \
    params_file:=$(pwd)/amr/config/map_merge_params.yaml \
    rviz_config:=$(pwd)/amr/rviz/merged_map.rviz \
    relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py \
    undock_script:=$(pwd)/amr/scripts/auto_undock.py \
    auto_undock:=true

옵션: robot11_y, rviz, merge_delay, venv_activate, auto_undock, undock_timeout
주의: 두 로봇이 도크에 물린 상태에서 실행할 것 (odom 원점 기준)
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def run_script(script, venv, name, extra_args=''):
    """venv가 있으면 activate 후, 스크립트를 실행하는 ExecuteProcess."""
    return ExecuteProcess(
        cmd=['bash', '-c',
             f'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; exec python3 "$0" {extra_args}',
             script, venv],
        name=name, output='log',
    )


def generate_launch_description():
    slam_launch = os.path.join(
        get_package_share_directory('turtlebot4_navigation'), 'launch', 'slam.launch.py')

    p = LaunchConfiguration('params_file')
    rviz_cfg = LaunchConfiguration('rviz_config')
    use_rviz = LaunchConfiguration('rviz')
    delay = LaunchConfiguration('merge_delay')
    y11 = LaunchConfiguration('robot11_y')
    relay = LaunchConfiguration('relay_script')
    venv = LaunchConfiguration('venv_activate')
    undock_script = LaunchConfiguration('undock_script')
    auto_undock = LaunchConfiguration('auto_undock')
    undock_timeout = LaunchConfiguration('undock_timeout')

    args = [
        DeclareLaunchArgument('params_file', description='map_merge 파라미터 파일 경로'),
        DeclareLaunchArgument('rviz_config', description='rviz 설정 파일 경로'),
        DeclareLaunchArgument('relay_script', description='tf_prefix_relay.py 경로'),
        DeclareLaunchArgument('venv_activate', default_value=''),
        DeclareLaunchArgument('undock_script', default_value=''),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('merge_delay', default_value='25.0'),
        DeclareLaunchArgument('robot11_y', default_value='4.58'),
        DeclareLaunchArgument('auto_undock', default_value='false'),
        DeclareLaunchArgument('undock_timeout', default_value='60.0'),
    ]

    def slam(ns, wait=0.0):
        inc = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(slam_launch),
            launch_arguments={'namespace': f'/{ns}'}.items())
        return TimerAction(period=wait, actions=[inc]) if wait else inc

    def static_tf(y, child, wait=0.0):
        node = Node(package='tf2_ros', executable='static_transform_publisher',
                    name=f'static_tf_{child.replace("/", "_")}',
                    arguments=['0', y, '0', '0', '0', '0', 'world', child], output='log')
        return TimerAction(period=wait, actions=[node]) if wait else node

    should_undock = PythonExpression(
        ["'", auto_undock, "' == 'true' and '", undock_script, "' != ''"])

    return LaunchDescription(args + [
        # SLAM
        slam('robot5'),
        slam('robot11', wait=5.0),

        # world -> robotN/map
        static_tf('0', 'robot5/map'),
        static_tf(y11, 'robot11/map', wait=2.0),

        # TF 접두사 중계
        TimerAction(period=3.0, actions=[run_script(relay, venv, 'tf_prefix_relay_robot5', '--ns robot5')]),
        TimerAction(period=8.0, actions=[run_script(relay, venv, 'tf_prefix_relay_robot11', '--ns robot11')]),

        # map_merge + rviz
        TimerAction(period=delay, actions=[
            Node(package='multirobot_map_merge', executable='map_merge',
                 name='map_merge', output='screen', parameters=[p]),
        ]),
        TimerAction(period=delay, actions=[
            Node(package='rviz2', executable='rviz2', name='rviz2_merged',
                 output='log', arguments=['-d', rviz_cfg], condition=IfCondition(use_rviz)),
        ]),

        # 자동 언도킹 (auto_undock:=true 이고 경로가 있을 때만)
        TimerAction(period=6.0, actions=[
            ExecuteProcess(
                cmd=['bash', '-c',
                     'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; exec python3 "$0" --timeout "$2"',
                     undock_script, venv, undock_timeout],
                name='auto_undock', output='screen', condition=IfCondition(should_undock)),
        ]),
    ])
