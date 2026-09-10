#!/usr/bin/env python3
"""
관제 PC 자동 실행 — world 정렬 + map_merge + rviz (+선택 자동 언도킹/지도 저장)

SLAM 도 TF 접두사 중계도 여기서 하지 않는다. 각 로봇 PC 가
amr/launch/robot_slam.launch.py 로 (SLAM + tf_prefix_relay) 를 한 묶음으로 띄우고,
전역 /tf 에 robot5/*, robot11/* 로 접두사가 붙은 프레임을 발행한다.
관제 PC 는 world 기준 정렬 static 만 걸고 /robot5/map, /robot11/map 을 병합한다.

전역 TF 트리:
  world ──(여기서 발행하는 static)──> <ns>/map ──(로봇 PC: slam)──> <ns>/odom
        ──(로봇 PC: create3)────────> <ns>/base_link ──> <ns>/rplidar_link ...
  * world->odom 은 절대 걸지 않는다. slam_toolbox 가 활성화 순간부터 map->odom
    (초기 identity) 을 계속 발행하므로 world->map 만 있으면 트리가 이어진다.
    예전에 world->odom / world->map 을 상황 보고 바꿔 걸던 게 부모 충돌의 원인이었다.

사용법:
  ros2 launch amr/launch/control_pc_full.launch.py \
    params_file:=$(pwd)/amr/config/map_merge_params.yaml \
    rviz_config:=$(pwd)/amr/rviz/merged_map.rviz \
    undock_script:=$(pwd)/amr/scripts/auto_undock.py \
    save_map_script:=$(pwd)/amr/scripts/save_merged_map.py \
    auto_undock:=true

save_map_script 를 주면, 두 로봇이 언도킹 주행을 마치고 다시 도킹을 완료했을 때
병합 지도(/map)를 map_output_dir 에 merged_map_name 이름으로 자동 저장한다.

옵션: robot11_y, rviz, merge_delay, venv_activate, auto_undock, undock_timeout,
      save_map_script, map_output_dir, merged_map_name
순서: 두 로봇 도크에 물린 상태 → 각 로봇 PC 에서 robot_slam.launch.py → 관제 PC 에서 이 launch
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    p = LaunchConfiguration('params_file')
    rviz_cfg = LaunchConfiguration('rviz_config')
    use_rviz = LaunchConfiguration('rviz')
    delay = LaunchConfiguration('merge_delay')
    y11 = LaunchConfiguration('robot11_y')
    venv = LaunchConfiguration('venv_activate')
    undock_script = LaunchConfiguration('undock_script')
    auto_undock = LaunchConfiguration('auto_undock')
    undock_timeout = LaunchConfiguration('undock_timeout')
    save_map_script = LaunchConfiguration('save_map_script')
    map_output_dir = LaunchConfiguration('map_output_dir')
    merged_map_name = LaunchConfiguration('merged_map_name')

    args = [
        DeclareLaunchArgument('params_file', description='map_merge 파라미터 파일 경로'),
        DeclareLaunchArgument('rviz_config', description='rviz 설정 파일 경로'),
        DeclareLaunchArgument('venv_activate', default_value=''),
        DeclareLaunchArgument('undock_script', default_value=''),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('merge_delay', default_value='25.0'),
        DeclareLaunchArgument('robot11_y', default_value='4.58'),
        DeclareLaunchArgument('auto_undock', default_value='false'),
        DeclareLaunchArgument('undock_timeout', default_value='60.0'),
        DeclareLaunchArgument('save_map_script', default_value=''),
        DeclareLaunchArgument('map_output_dir', default_value='amr/maps'),
        DeclareLaunchArgument('merged_map_name', default_value='merged_map'),
    ]

    def static_tf(y, child, wait=0.0):
        node = Node(package='tf2_ros', executable='static_transform_publisher',
                    name=f'static_tf_{child.replace("/", "_")}',
                    arguments=['0', y, '0', '0', '0', '0', 'world', child], output='log')
        return TimerAction(period=wait, actions=[node]) if wait else node

    should_undock = PythonExpression(
        ["'", auto_undock, "' == 'true' and '", undock_script, "' != ''"])

    should_save_map = PythonExpression(["'", save_map_script, "' != ''"])

    return LaunchDescription(args + [
        # SLAM · tf_prefix_relay 는 각 로봇 PC 의 robot_slam.launch.py 에서 실행한다.

        # world 기준 정렬 — 로봇5 도크를 원점, 로봇11 도크를 (0, robot11_y, 0) 으로.
        # world->map 만 건다 (world->odom 금지: slam_toolbox 가 map->odom 을 발행).
        static_tf('0', 'robot5/map'),
        static_tf(y11, 'robot11/map', wait=2.0),

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

        # 병합 지도 자동 저장 (save_map_script 경로가 있을 때만)
        # 두 로봇이 언도킹 주행 후 다시 도킹을 마치면 /map 을 저장한다
        TimerAction(period=delay, actions=[
            ExecuteProcess(
                cmd=['bash', '-c',
                     'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; '
                     'exec python3 "$0" --output-dir "$2" --name "$3"',
                     save_map_script, venv, map_output_dir, merged_map_name],
                name='save_merged_map', output='screen',
                condition=IfCondition(should_save_map)),
        ]),
    ])
