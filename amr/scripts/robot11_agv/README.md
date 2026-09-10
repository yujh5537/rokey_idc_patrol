# robot11 고정 순서 주행

기준 main: `53fded2768bca365723d7635823a16f95186ff16` (MAP-02 PR #8 병합).
브랜치: `euiseok/20260909-agv-robot11-z4-route`.

robot11이 map 좌표 세 곳을 순서대로 방문하고 Z4 입구에서 종료한다.

| 순서 | x m | y m | 도착 yaw | 의미 |
|---|---:|---:|---:|---|
| 1 | 0.270 | 2.625 | -π/2 | 두 도크 초기 위치의 중점 |
| 2 | 1.400 | 2.800 | 0 | Z2·Z3 입구의 중점 |
| 3 | 1.400 | 0.700 | 0 | Z4 입구 |

첫 두 목표의 yaw는 이 데모에서 정한 도착 방향이다. 마지막은 Z4 entry_pose 방향이다.
각 목표 성공 후 2초 대기한다. 실패/거부/취소 시 다음 목표를 보내지 않는다.
목표당 제한은 180초. `--goal-timeout 240 --dwell 3`처럼 변경 가능하다.
Nav2 NavigateToPose를 순서대로 호출하는 고정 순서 데모이며 직선 궤적을 강제하지 않는다.
중간 벽 x=0.8, 개구부 y=2.4~3.2를 통과하는 실제 경로는 Nav2가 계획한다.
도착 오차·속도·장애물 회피 설정은 현재 Nav2 설정을 따른다.
랙 검사, 자동 도킹, 초기 위치 강제 재설정, robot5 제어는 수행하지 않는다.

## 1 코드 받기

ROS가 설치된 제어 PC에서 진행한다. PC4 웹 서버에서는 실행하지 않는다.
기존 변경 파일이 있으면 먼저 별도 커밋 등으로 보관한다. 강제 checkout하지 않는다.

```bash
cd ~/collaboration/rokey_idc_patrol
git status --short
git fetch origin
git switch --track origin/euiseok/20260909-agv-robot11-z4-route
```

이미 로컬 브랜치가 있으면 `git switch euiseok/20260909-agv-robot11-z4-route` 후 `git pull --ff-only`.

## 2 준비

각 터미널에서 Jazzy와 워크스페이스를 source한다. 기존에 정상 통신하던 Discovery 설정을 사용한다.
robot11의 SLAM/AMCL/Nav2를 여러 PC에서 중복 실행하지 않는다. 다른 미션/teleop 목표 전송도 중지한다.
Z4는 기존 robot5 담당 영역이므로 이번 단독 주행 중 robot5는 경로 밖에 정지시킨다.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/collaboration/rokey_idc_patrol
export ROS_DOMAIN_ID=2
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
sudo apt install ros-jazzy-nav2-msgs
colcon build --symlink-install --packages-select idc_bringup
source install/setup.bash
python3 scripts/robot11_agv/route.py
```

마지막 명령은 좌표만 출력하며 ROS 연결/주행을 하지 않는다. 스크립트는 별도 setup.py 등록 없이 실행한다.
`rclpy`, `action_msgs`는 ROS Jazzy 환경, `nav2_msgs`는 위 패키지를 사용한다.

## 3 정적 지도 측위와 Nav2

이미 robot11이 동일 MAP-02 지도로 정상 측위/주행 중이면 해당 프로세스를 그대로 사용한다.
새로 시작할 경우 아래 두 명령을 각각 별도 터미널에서 실행한다(각 터미널 source 필요).

```bash
ros2 launch turtlebot4_navigation localization.launch.py namespace:=/robot11 \
  map:=$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
```

```bash
ros2 launch turtlebot4_navigation nav2.launch.py namespace:=/robot11
```

## 4 초기 위치 확인과 언도킹

로봇이 실제로 지정된 robot11 도크 중심 `(0.27,4.92)`에 있고 왼쪽을 보는 경우에만 다음 초기 위치를 발행한다.
이미 다른 위치라면 RViz의 2D Pose Estimate로 실제 위치/방향을 지정한다.
RViz에서 map과 robot11 LaserScan이 벽·랙에 겹치는지 확인한다.

```bash
ros2 topic pub --once /robot11/initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  '{header: {frame_id: map}, pose: {pose: {position: {x: 0.27, y: 4.92}, orientation: {z: 1.0, w: 0.0}}, covariance: [0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0685]}}'
```

도킹 상태이면 언도킹을 한 번 실행하고 SUCCEEDED 및 결과 is_docked=false를 확인한다.
이미 언도킹 상태라면 생략한다. 언도킹 후 옛 도크 좌표로 initialpose를 다시 덮어쓰지 않는다.

```bash
ros2 action send_goal /robot11/undock irobot_create_msgs/action/Undock '{}' --feedback
ros2 lifecycle get /robot11/amcl
ros2 lifecycle get /robot11/bt_navigator
ros2 action info /robot11/navigate_to_pose
ros2 topic echo /robot11/amcl_pose --once
```

AMCL과 bt_navigator가 active, NavigateToPose 서버 1개, 현재 pose가 실물과 일치해야 한다.
초기/현재 위치는 스크립트가 자동 검증하지 않으며 사용자가 RViz에서 확인한다.

## 5 주행

```bash
python3 scripts/robot11_agv/route.py --execute
```

GO dock_midpoint → ARRIVED → 2초 → GO z2_z3_midpoint → ARRIVED → 2초 →
GO z4_entry → ARRIVED → 2초 → ROUTE COMPLETE 순으로 출력한다.
실행할 때마다 첫 목표부터 시작한다. 실패 후 재실행 전 현재 위치와 장애물을 확인한다.

Ctrl+C는 현재 목표 취소를 요청한다. 통신 단절로 취소 결과를 확인할 수 없으면
`STOP UNCONFIRMED` 또는 `Goal acceptance unknown`이 출력될 수 있다.
그 경우 물리 정지 버튼으로 멈추고 Nav2 상태를 확인한다. 프로세스 종료만으로 정지를 보장하지 않는다.
같은 PC의 중복 스크립트는 잠금으로 방지하지만 다른 PC/미션 노드의 목표는 차단하지 않는다.

## 검증 범위

```bash
python3 -m unittest discover -s scripts/robot11_agv -v
python3 -m py_compile scripts/robot11_agv/route.py
```

순서, 실패 시 중단, 대기 중 중단, 잘못된 시간 인자 검증을 수행했다.
개발 환경에 ROS 2/실물이 없어 DDS, Action 통신, 취소 동작, 실기 도달은 아직 검증하지 않았다.
