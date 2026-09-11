#!/usr/bin/env python3
"""
관제 PC 자동 실행 — world 정렬 + 지도 병합 + rviz (+선택 자동 언도킹/지도 저장)

SLAM 도 TF 접두사 중계도 여기서 하지 않는다. 각 로봇 PC 가
amr/launch/robot_slam.launch.py 로 (SLAM + tf_prefix_relay) 를 한 묶음으로 띄우고,
전역 /tf 에 robot5/*, robot11/* 로 접두사가 붙은 프레임을 발행한다.
관제 PC 는 world 기준 정렬 static 만 걸고 /robot5/map, /robot11/map 을 병합한다.

전역 TF 트리:
  world ──(여기서 발행하는 static)──> <ns>/map ──(로봇 PC: slam)──> <ns>/odom
        ──(로봇 PC: create3)────────> <ns>/base_link ──> <ns>/rplidar_link ...
  * world->odom 은 절대 걸지 않는다. slam_toolbox 가 활성화 순간부터 map->odom
    (초기 identity) 을 계속 발행하므로 world->map 만 있으면 트리가 이어진다.

■ 좌표 정렬 (로봇 좌표 ↔ 병합 지도가 안 맞는 문제)
  기본은 amr/scripts/merge_maps_world.py (직접 래스터화) 로 병합한다. 이 노드는
  world<-robotN/map 변환(= static TF world->robotN/map 인자)과 각 입력 그리드의
  info.origin 을 미터 단위로 정확히 적용하고, 출력 /map 의 info.origin 에 실제 world
  좌표를 넣어 world 프레임으로 발행한다. → 로봇 TF 와 /map 이 같은 world 기준으로 정렬.

  multirobot_map_merge(m-explore-ros2) 는 known_init_poses 모드에서
    - init_pose 이동값을 픽셀로 적용(미터 아님), 회전 중심이 픽셀 (0,0) 모서리,
    - 출력 origin 을 항상 (-w/2, -h/2, yaw=0) 으로 강제
  하므로 /map 이 world 기준으로 어긋난다. merge_script 를 비우면 fallback 으로
  이 패키지를 쓰지만 정렬은 보장되지 않는다.

  r5_*, r11_* 인자 하나로 static TF 와 병합 노드의 pose 를 동시에 세팅한다
  (좌표 단일 소스). 기본 좌표계(정면 +x, 왼쪽 +y)에서 x·y 를 180° 돌린 좌표계라
  r5_yaw, r11_yaw 기본값 = π (3.14159265). 도크 배치가 다르면 인자로 조정.

사용법:
  ros2 launch amr/launch/control_pc_full.launch.py \
    merge_script:=$(pwd)/amr/scripts/merge_maps_world.py \
    rviz_config:=$(pwd)/amr/rviz/merged_map.rviz \
    undock_script:=$(pwd)/amr/scripts/auto_undock.py \
    save_map_script:=$(pwd)/amr/scripts/save_merged_map.py \
    auto_undock:=true
  # 좌표 조정 예: r11_y:=4.53 r11_yaw:=3.14159265
  # params_file:= 는 fallback(multirobot_map_merge) 을 쓸 때만 필요

옵션: r5_x r5_y r5_yaw r11_x r11_y r11_yaw, merge_script, merge_rate, rviz,
      merge_delay, venv_activate, auto_undock, undock_timeout, save_map_script,
      map_output_dir, merged_map_name, params_file(fallback 전용)
순서: 두 로봇 도크에 물린 상태 → 각 로봇 PC 에서 robot_slam.launch.py → 관제 PC 에서 이 launch
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml

# π — 기본 좌표계에서 x·y 를 180° 회전한 좌표계
YAW_180 = '3.14159265'

# fallback(multirobot_map_merge) 기본 파라미터 (cwd 무관하게 이 파일 기준 경로)
_DEFAULT_MAP_MERGE_PARAMS = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'config', 'map_merge_params.yaml'))


def generate_launch_description():
    p = LaunchConfiguration('params_file')
    merge_script = LaunchConfiguration('merge_script')
    merge_rate = LaunchConfiguration('merge_rate')
    rviz_cfg = LaunchConfiguration('rviz_config')
    use_rviz = LaunchConfiguration('rviz')
    delay = LaunchConfiguration('merge_delay')
    venv = LaunchConfiguration('venv_activate')
    undock_script = LaunchConfiguration('undock_script')
    auto_undock = LaunchConfiguration('auto_undock')
    undock_timeout = LaunchConfiguration('undock_timeout')
    save_map_script = LaunchConfiguration('save_map_script')
    map_output_dir = LaunchConfiguration('map_output_dir')
    merged_map_name = LaunchConfiguration('merged_map_name')

    r5_x, r5_y, r5_yaw = (LaunchConfiguration(k) for k in ('r5_x', 'r5_y', 'r5_yaw'))
    r11_x, r11_y, r11_yaw = (LaunchConfiguration(k) for k in ('r11_x', 'r11_y', 'r11_yaw'))

    args = [
        DeclareLaunchArgument(
            'merge_script', default_value='',
            description='amr/scripts/merge_maps_world.py 경로. 비우면 fallback 으로 '
                        'multirobot_map_merge 사용 (정렬 보장 안 됨).'),
        DeclareLaunchArgument('merge_rate', default_value='2.0',
                              description='merge_maps_world 발행 주기 Hz'),
        DeclareLaunchArgument('params_file', default_value=_DEFAULT_MAP_MERGE_PARAMS,
                              description='multirobot_map_merge 파라미터 파일 (fallback 전용)'),
        DeclareLaunchArgument('rviz_config', description='rviz 설정 파일 경로'),
        DeclareLaunchArgument('venv_activate', default_value=''),
        DeclareLaunchArgument('undock_script', default_value=''),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('merge_delay', default_value='25.0'),
        DeclareLaunchArgument('auto_undock', default_value='false'),
        DeclareLaunchArgument('undock_timeout', default_value='60.0'),
        DeclareLaunchArgument('save_map_script', default_value=''),
        DeclareLaunchArgument('map_output_dir', default_value='amr/maps'),
        DeclareLaunchArgument('merged_map_name', default_value='merged_map'),
        # world -> robotN/map = map_merge init_pose (둘이 항상 일치)
        DeclareLaunchArgument('r5_x', default_value='0.0'),
        DeclareLaunchArgument('r5_y', default_value='0.0'),
        DeclareLaunchArgument('r5_yaw', default_value=YAW_180),
        DeclareLaunchArgument('r11_x', default_value='0.0'),
        DeclareLaunchArgument('r11_y', default_value='4.53'),  # 로봇11 도크 실측 (world y)
        DeclareLaunchArgument('r11_yaw', default_value=YAW_180),
    ]

    def static_tf(x, y, yaw, child, wait=0.0):
        node = Node(
            package='tf2_ros', executable='static_transform_publisher',
            name=f'static_tf_{child.replace("/", "_")}', output='log',
            arguments=['--x', x, '--y', y, '--z', '0.0',
                       '--yaw', yaw, '--pitch', '0.0', '--roll', '0.0',
                       '--frame-id', 'world', '--child-frame-id', child])
        return TimerAction(period=wait, actions=[node]) if wait else node

    # fallback(multirobot_map_merge) 전용: init_pose_* 를 static 과 같은 값으로 덮어쓴다
    merge_params = RewrittenYaml(
        source_file=p, root_key='', convert_types=True,
        param_rewrites={
            '/robot5/map_merge/init_pose_x': r5_x,
            '/robot5/map_merge/init_pose_y': r5_y,
            '/robot5/map_merge/init_pose_yaw': r5_yaw,
            '/robot11/map_merge/init_pose_x': r11_x,
            '/robot11/map_merge/init_pose_y': r11_y,
            '/robot11/map_merge/init_pose_yaw': r11_yaw,
        })

    should_undock = PythonExpression(
        ["'", auto_undock, "' == 'true' and '", undock_script, "' != ''"])
    should_save_map = PythonExpression(["'", save_map_script, "' != ''"])
    use_world_merger = PythonExpression(["'", merge_script, "' != ''"])
    use_map_merge = PythonExpression(["'", merge_script, "' == ''"])

    return LaunchDescription(args + [
        # SLAM · tf_prefix_relay 는 각 로봇 PC 의 robot_slam.launch.py 에서.

        # world 기준 정렬 (world->map 만; world->odom 금지)
        static_tf(r5_x, r5_y, r5_yaw, 'robot5/map'),
        static_tf(r11_x, r11_y, r11_yaw, 'robot11/map', wait=2.0),

        # 지도 병합 — 기본: merge_maps_world.py (world 정렬), fallback: multirobot_map_merge
        TimerAction(period=delay, actions=[
            ExecuteProcess(
                cmd=['bash', '-c',
                     'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; '
                     'exec python3 "$0" '
                     '--pose robot5 "$2" "$3" "$4" '
                     '--pose robot11 "$5" "$6" "$7" '
                     '--map-topic map --merged-topic /map --world-frame world '
                     '--rate "$8"',
                     merge_script, venv,
                     r5_x, r5_y, r5_yaw, r11_x, r11_y, r11_yaw, merge_rate],
                name='merge_maps_world', output='screen',
                condition=IfCondition(use_world_merger)),
            Node(package='multirobot_map_merge', executable='map_merge',
                 name='map_merge', output='screen', parameters=[merge_params],
                 condition=IfCondition(use_map_merge)),
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
