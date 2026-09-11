#!/usr/bin/env python3
"""
관제 PC — 순찰 시작 (Phase 2, patrol_bringup.launch.py 이후).

patrol_bringup 으로 localization+Nav2 가 뜨고, 각 RViz 에서 2D Pose Estimate 로 두 로봇의
언도킹 실제 위치를 지정한 뒤 실행한다. 두 순찰 스크립트를 시차를 두고 --execute 로 띄운다.

  T+0s          : lead 로봇   (기본 robot5 = robot5_agv/robot5_patrol.py)
  T+lead_delay  : 나머지 로봇 (robot11 = robot11_agv/patrol.py)

  robot5_patrol.py : 단순형. 스스로 언도킹하지 않는다 → 먼저 수동 언도킹해 둘 것.
  robot11 patrol.py: 언도킹 상태면 언도킹 액션을 생략하고 준비 확인부터 한다.

두 스크립트 모두 출발 전 MAP-02 규격·최신 TF·언도킹 상태·도크 0.8m 이내를 검사하고
하나라도 아니면 아무 목표도 보내지 않는다(안전).

사용:
  ros2 launch amr/launch/patrol_start.launch.py
  ros2 launch amr/launch/patrol_start.launch.py lead_delay:=10.0 dwell:=5.0
  ros2 launch amr/launch/patrol_start.launch.py lead:=robot11
  ros2 launch amr/launch/patrol_start.launch.py venv_activate:=$HOME/venvs/rokey_venv/bin/activate
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, TimerAction
from launch.substitutions import LaunchConfiguration

_AMR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# ns -> 순찰 스크립트 (관제 PC 에서 python3 로 직접 실행; amr 는 ROS 패키지가 아님)
SCRIPTS = {
    'robot5': os.path.join(_AMR, 'scripts', 'robot5_agv', 'robot5_patrol.py'),
    'robot11': os.path.join(_AMR, 'scripts', 'robot11_agv', 'patrol.py'),
}


def _setup(context, *_args, **_kwargs):
    lead = LaunchConfiguration('lead').perform(context)
    lead_delay = float(LaunchConfiguration('lead_delay').perform(context))
    dwell = LaunchConfiguration('dwell').perform(context)
    venv = LaunchConfiguration('venv_activate').perform(context)

    if lead not in SCRIPTS:
        raise RuntimeError(f"lead 는 {list(SCRIPTS)} 중 하나여야 함 (받은 값: {lead!r})")

    actions = []
    for ns, script in SCRIPTS.items():
        period = 0.0 if ns == lead else lead_delay
        actions.append(TimerAction(period=period, actions=[ExecuteProcess(
            cmd=['bash', '-c',
                 'if [ -n "$1" ]; then source "$1" 2>/dev/null; fi; '
                 'exec python3 "$0" --execute --dwell "$2"',
                 script, venv, dwell],
            name=f'patrol_{ns}', output='screen')]))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('lead', default_value='robot5',
                              description='먼저 출발하는 로봇 (robot5 | robot11)'),
        DeclareLaunchArgument('lead_delay', default_value='5.0',
                              description='두 번째 로봇 출발까지 지연(초)'),
        DeclareLaunchArgument('dwell', default_value='3.0',
                              description='랙마다 대기(초)'),
        DeclareLaunchArgument('venv_activate', default_value='',
                              description='스크립트 실행 전 source 할 venv activate 경로(선택)'),
        OpaqueFunction(function=_setup),
    ])
