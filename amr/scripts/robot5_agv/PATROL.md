# robot5 Z4·Z3 순찰 + 도킹

실행 파일은 `patrol.py`입니다. `scripts/robot11_agv/patrol.py`와 동일한 구조이며
robot5(중간 벽 아래 도크, 담당 구역 Z4·Z3)에 맞춰 좌표·네임스페이스만 바꿨습니다.
이번 코드는 28개 랙의 이동·방향 정렬·3초 대기만 수행합니다. 카메라/도어/LED 판정은
`inspect(rack_id)`에 TODO 주석으로 표시했습니다. 정상 판정 결과를 만들지 않습니다.

## 확정 경로

좌표는 `src/idc_bringup/config/racks.yaml`의 map 프레임(m, rad) 기준입니다.
순찰 순서는 `patrol_routes.robot5`(PM 확정 9/9)입니다.

1. 도크 바로 앞 `(0.270, 0.330)`에서 언도킹 완료 및 위치 추정 확인 후 시작합니다.
2. `(0.270, 2.625)`(두 도크 중점) → `(1.400, 2.800)`(중간 벽 개구부 통과) → Z4 진입 `(1.400, 0.700)`.
3. Z4: R56 → R55 → R54 → R53 → R52 → R51 → R50 → R43 → R44 → R45 → R46 → R47 → R48 → R49.
4. Z4 출구 `(1.400, 0.700)` → Z3 진입 `(1.400, 2.100)`.
5. Z3: R42 → R41 → R40 → R39 → R38 → R37 → R36 → R29 → R30 → R31 → R32 → R33 → R34 → R35.
6. Z3 출구 `(1.400, 2.100)` → `(1.400, 2.800)` → `(0.270, 2.625)` → 시작 시 기록한 도크 앞 위치.
7. `/robot5/dock` (`irobot_create_msgs/action/Dock`) 실행.
   액션 SUCCEEDED **및** 결과 `is_docked=true`일 때만 전체 완료입니다.

중간 벽은 x=0.8, 개구부는 y=2.4~3.2입니다. robot5 도크는 개구부 아래에 있으므로 왼쪽
복도(x≈0.27)로 개구부까지 올라간 뒤 x=1.4에서 랙 구역으로 건너갑니다. 복귀도 같은
개구부를 되짚습니다. 랙들을 역순으로 재점검하지 않으며 Nav2가 좌표 사이 경로를 계획합니다.
저장된 도크 좌표 `(0.270,0.330)`는 위치 확인에만 쓰고 충전 접점으로 Nav2 목표를 보내지
않습니다. 설정 도크에서 0.8m 넘게 떨어진 시작은 거부합니다.

## 실행 순서와 터미널

이미 서비스가 동작 중이면 중복 실행하지 않습니다. 공통 준비:

```bash
source /opt/ros/jazzy/setup.bash
source ~/turtlebot4_ws/install/setup.bash
cd ~/collaboration/rokey_idc_patrol
source install/setup.bash
export ROS_DOMAIN_ID=2
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

환경에 PyYAML, rclpy, tf2_ros, nav2_msgs, irobot_create_msgs가 필요합니다.
Python 스크립트 변경이므로 새 colcon 빌드는 필요 없습니다.

### 1번 — 지도 + AMCL (계속 유지)

```bash
ros2 launch turtlebot4_navigation localization.launch.py \
  namespace:=/robot5 \
  map:=$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
```

### 2번 — RViz (계속 유지)

```bash
rviz2 --ros-args \
  -r /initialpose:=/robot5/initialpose \
  -r /tf:=/robot5/tf \
  -r /tf_static:=/robot5/tf_static
```

Fixed Frame=`map`, Map=`/robot5/map`(Transient Local), LaserScan=`/robot5/scan`.
언도킹 뒤 **현재 실제 위치·방향**을 2D Pose Estimate로 지정하고 라이다 정합을 확인합니다.
경로 첫 목표를 초기 위치로 넣지 않습니다.

### 3번 — 언도킹만 수행

도크 출구를 확보한 뒤:

```bash
python3 scripts/robot5_agv/patrol.py --execute --undock-only
```

이미 언도킹 상태면 언도킹 액션을 반복하지 않습니다.

### 4번 — Nav2 (계속 유지)

반드시 robot5 전용 프로필로 시작합니다. 실행 중인 Nav2에는 파일 수정이 자동 반영되지
않으므로 정지 후 재시작합니다.

```bash
ros2 launch turtlebot4_navigation nav2.launch.py namespace:=/robot5 \
  params_file:="$PWD/scripts/robot5_agv/nav2_patrol.yaml"
```

### 5번 — 준비 확인 → 미리보기 → 순찰 시작

```bash
timeout 10s ros2 lifecycle get /robot5/amcl
timeout 10s ros2 lifecycle get /robot5/bt_navigator
timeout 10s ros2 lifecycle get /robot5/controller_server
timeout 10s ros2 lifecycle get /robot5/planner_server
python3 scripts/robot5_agv/patrol.py
```

마지막 명령은 좌표만 출력하며 ROS 연결/주행을 하지 않습니다. 관리 노드가 모두
`active [3]`, 위치·라이다 정합이 확인되면:

```bash
python3 scripts/robot5_agv/patrol.py --execute --dwell 3
```

이 명령은 **28개 랙 순찰부터 최종 도킹까지** 수행합니다. 같은 시간에 teleop, RViz
목표, 다른 mission client를 실행하지 않습니다. robot11은 공용 통로 밖에 둡니다.

랙마다 TURN_TO_TRAVEL(이동 방향 회전) → MOVE(점검 위치 이동) → FACE_RACK(랙 방향
회전) → DWELL(3초 대기)를 순서대로 실행합니다. 이동은 NavigateToPose, 회전은 충돌
검사를 유지하는 Nav2 Spin 액션입니다. 목표까지 8cm 이내면 이동을 생략하고 랙 방향만
맞춥니다. 회전 차이가 8도 이내면 회전도 생략합니다. R50→R43, R36→R29는 동일 XY이므로
보통 방향만 바꿉니다.

도킹 중에 `--execute`만 실행하면 자동 언도킹 후 준비 상태를 최대 180초 기다립니다
(`--ready-timeout`로 조정). 초기 pose는 코드가 자동으로 지정하지 않습니다.

## 중단과 종료

- 중단: 실행 터미널에서 Ctrl+C. 현재 액션 취소를 요청하며 이후 목표·도킹을 차단합니다.
- `STOP UNCONFIRMED` / `Goal acceptance unknown`이면 물리 정지 버튼으로 멈추고 Nav2 상태를 확인합니다.
- 재실행은 중간 재개가 아닙니다. 다시 언도킹한 도크 앞에서 시작합니다.
- 같은 PC의 중복 스크립트는 `/tmp/idc_robot5_route_<uid>.lock`으로 방지합니다.

## 검증 범위

```bash
python3 -m unittest discover -s scripts/robot5_agv -v
python3 -m py_compile scripts/robot5_agv/patrol.py
```

경로/28개 랙 순서/구역 간 출구/복귀 순서, 각 이동 단계 실패 차단, 정차 중단, 도킹 실패
처리, 언도킹 분기와 실패 차단의 자동 테스트를 통과했습니다. 미리보기와 Python 구문도
확인했습니다. 개발 환경에 ROS 2/실물이 없어 DDS, Action 통신, 취소 동작, 실기 도달·자동
도킹은 아직 검증하지 않았습니다.
