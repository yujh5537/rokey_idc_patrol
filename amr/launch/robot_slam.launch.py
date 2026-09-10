#!/usr/bin/env python3
"""
robot_slam.launch.py — 로봇 PC 1대에서 실행 (robot5 PC, robot11 PC 각각 1번씩)

한 로봇의 SLAM 과 TF 접두사 중계를 한 묶음으로 띄운다.
= 중계 노드를 매번 따로 켤 필요가 없다. 중계가 죽어도 respawn 으로 살아난다.

구성:
  1. turtlebot4_navigation/slam.launch.py 를 namespace 로 include
     -> /<ns>/map, /<ns>/tf 에 SLAM 발행 (프레임 이름엔 접두사 없음: map, odom, base_link)
  2. tf_prefix_relay: /<ns>/tf(_static) 의 모든 프레임에 "<ns>/" 를 붙여
     전역 /tf(_static) 로 재발행 (respawn=true)
  3. (기본 on) 스캔 frame_id 를 <ns>/<lidar_link> 로 보정해 /<ns>/<scan_ns_topic> 로 재발행
     -> 관제 PC rviz(전역 TF) 에서도 스캔이 보인다

전역 TF 트리 (관제 PC 기준):
  world ──(control_pc_full 의 static)──> <ns>/map
        ──(slam_toolbox: map->odom)────> <ns>/odom
        ──(create3: odom->base_link)───> <ns>/base_link ──> <ns>/rplidar_link ...
  * world->odom 을 직접 걸지 않는다. slam_toolbox 가 활성화 순간부터 map->odom(초기 identity)
    을 계속 발행하므로 world->map 만 있으면 트리가 이어진다. (예전에 world->odom 과
    world->map 을 상황따라 바꿔 걸던 게 프레임 부모 충돌의 원인이었음)

사용법:
  # robot5 PC
  ros2 launch amr/launch/robot_slam.launch.py namespace:=robot5 \
    relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py
  # robot11 PC
  ros2 launch amr/launch/robot_slam.launch.py namespace:=robot11 \
    relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py

관제 PC 는 amr/launch/control_pc_full.launch.py (world 정렬 + map_merge + rviz).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _setup(context, *args, **kwargs):
    ns = LaunchConfiguration('namespace').perform(context).lstrip('/')
    relay_script = LaunchConfiguration('relay_script').perform(context)
    venv = LaunchConfiguration('venv_activate').perform(context)
    sync = LaunchConfiguration('sync').perform(context)
    fix_scan = LaunchConfiguration('fix_scan').perform(context).lower() in ('1', 'true', 'yes')
    lidar_link = LaunchConfiguration('lidar_link').perform(context)
    scan_ns_topic = LaunchConfiguration('scan_ns_topic').perform(context)

    slam_launch = os.path.join(
        get_package_share_directory('turtlebot4_navigation'), 'launch', 'slam.launch.py')

    relay_cmd = 'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; ' \
                f'exec python3 "$0" --ns {ns}'
    if fix_scan:
        relay_cmd += f' --scan-out {scan_ns_topic} --lidar-link {lidar_link}'

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(slam_launch),
            launch_arguments={'namespace': f'/{ns}', 'sync': sync}.items()),

        ExecuteProcess(
            cmd=['bash', '-c', relay_cmd, relay_script, venv],
            name=f'tf_prefix_relay_{ns}', output='screen',
            respawn=True, respawn_delay=2.0),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('namespace', description='로봇 네임스페이스 (robot5 / robot11)'),
        DeclareLaunchArgument('relay_script', description='amr/scripts/tf_prefix_relay.py 경로'),
        DeclareLaunchArgument('venv_activate', default_value='',
                              description='relay 실행 전 source 할 venv activate 경로 (선택)'),
        DeclareLaunchArgument('sync', default_value='true', choices=['true', 'false'],
                              description='slam_toolbox 동기 모드 여부'),
        DeclareLaunchArgument('fix_scan', default_value='true', choices=['true', 'false'],
                              description='스캔 frame_id 를 <ns>/<lidar_link> 로 보정해 재발행'),
        DeclareLaunchArgument('lidar_link', default_value='rplidar_link',
                              description='라이다 링크 이름'),
        DeclareLaunchArgument('scan_ns_topic', default_value='scan_ns',
                              description='보정된 스캔 토픽 이름 (<ns>/ 뒤)'),
        OpaqueFunction(function=_setup),
    ])
