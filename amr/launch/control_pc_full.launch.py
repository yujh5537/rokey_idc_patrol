#!/usr/bin/env python3
"""
관제 PC 자동 실행 — TF 정렬 + map_merge + rviz (+선택 자동 언도킹)

SLAM은 관제 PC 과부하 때문에 여기서 실행하지 않는다.
각 로봇 PC 두 대에서 개별로 slam.launch.py 를 띄우고
(robot5 → /robot5/map, robot11 → /robot11/map), 관제 PC는 그 지도를 받아
정렬·병합만 한다.

사용법:
  ros2 launch amr/launch/control_pc_full.launch.py \
    params_file:=$(pwd)/amr/config/map_merge_params.yaml \
    rviz_config:=$(pwd)/amr/rviz/merged_map.rviz \
    relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py \
    undock_script:=$(pwd)/amr/scripts/auto_undock.py \
    auto_undock:=true

옵션: robot11_y, rviz, merge_delay, venv_activate, auto_undock, undock_timeout
주의: 두 로봇이 도크에 물린 상태에서, 각 로봇 PC의 SLAM이 올라온 뒤 실행할 것 (odom 원점 기준)
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition
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

    def static_tf(y, child, wait=0.0):
        node = Node(package='tf2_ros', executable='static_transform_publisher',
                    name=f'static_tf_{child.replace("/", "_")}',
                    arguments=['0', y, '0', '0', '0', '0', 'world', child], output='log')
        return TimerAction(period=wait, actions=[node]) if wait else node

    should_undock = PythonExpression(
        ["'", auto_undock, "' == 'true' and '", undock_script, "' != ''"])

    return LaunchDescription(args + [
        # SLAM은 각 로봇 PC에서 실행 — 여기서는 띄우지 않는다

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
