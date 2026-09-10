# robot11 Z1·Z2 순찰 + 도킹

실행 파일은 `patrol.py`입니다. 기존 `route.py`는 Z4 이동 시험용으로 유지합니다.
이번 코드는 28개 랙의 이동·방향 정렬·3초 대기만 수행합니다. 카메라/도어/LED 판정은
`patrol.py`의 `inspect(rack_id)`에 TODO 주석으로 표시했습니다. 정상 판정 결과를 만들지 않습니다.

## 확정 경로

좌표는 `src/idc_bringup/config/racks.yaml`의 map 프레임(m, rad) 기준입니다.

1. 도크 바로 앞에서 언도킹 완료 및 위치 추정 확인 후 시작합니다.
2. `(0.270, 2.625)` → `(1.400, 2.800)` → Z1 진입 `(1.400, 4.900)`.
3. Z1: R07 → R06 → R05 → R04 → R03 → R02 → R01 → R08 → R09 → R10 → R11 → R12 → R13 → R14.
4. Z1 출구 `(1.400, 4.900)` → Z2 진입 `(1.400, 3.500)`.
5. Z2: R21 → R20 → R19 → R18 → R17 → R16 → R15 → R22 → R23 → R24 → R25 → R26 → R27 → R28.
6. Z2 출구 `(1.400, 3.500)` → `(1.400, 2.800)` → `(0.270, 2.625)` → 시작 시 기록한 도크 앞 위치.
7. `/robot11/dock` (`irobot_create_msgs/action/Dock`) 실행.
   액션 SUCCEEDED **및** 결과 `is_docked=true`일 때만 전체 완료입니다.

복귀는 접근 통로 좌표를 되짚습니다. 랙들을 역순으로 재점검하지 않습니다.
Nav2가 좌표 사이의 경로를 다시 계획하므로 실제 궤적을 그대로 재생하는 방식은 아닙니다.
저장된 도크 좌표 `(0.270,4.920)`는 위치 확인에 사용하며, 충전 접점으로 Nav2 목표를 보내지 않습니다.
도크 앞 시작 위치는 실행마다 map→base_link TF로 기록합니다. 실제 도크에서 언도킹한 직후
시작하고, 도크를 옮겼다면 지도/설정부터 맞추세요. 설정 도크에서 0.8m 넘게 떨어진 시작은 거부합니다.

## 코드 받기 — PC3 명령 터미널

기존 작업을 저장하고 자율주행/teleop를 종료한 상태에서 실행합니다.

```bash
cd ~/collaboration/rokey_idc_patrol
git fetch origin
git switch --track origin/euiseok/20260909-robot11-z1-z2-patrol
```

이미 해당 브랜치가 있으면 `git switch euiseok/20260909-robot11-z1-z2-patrol` 후
`git pull --ff-only`를 사용합니다. Python 스크립트 변경이므로 새 colcon 빌드는 필요 없습니다.
환경에 PyYAML, rclpy, tf2_ros, nav2_msgs, irobot_create_msgs가 필요합니다.

## 실행 순서와 터미널

이미 서비스가 동작 중이면 중복 실행하지 않습니다.
터미널 2~5의 공통 준비는 다음과 같습니다. 기존에 통신이 된 ROS_DISCOVERY_SERVER 설정을 유지합니다.

```bash
source /opt/ros/jazzy/setup.bash
source ~/turtlebot4_ws/install/setup.bash
cd ~/collaboration/rokey_idc_patrol
source install/setup.bash
export ROS_DOMAIN_ID=2
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

### 1번 — Discovery Server (계속 유지)

11811 포트에 기존 서버가 없을 때만 시작합니다. `unset`은 이 터미널에만 적용합니다.

```bash
source /opt/ros/jazzy/setup.bash
ss -lunp | grep ':11811'
# 서버가 없을 때:
unset ROS_DISCOVERY_SERVER
fastdds discovery --server-id 0
```

### 2번 — 지도 + AMCL (계속 유지)

```bash
ros2 launch turtlebot4_navigation localization.launch.py \
  namespace:=/robot11 \
  map:=$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
```

### 3번 — RViz (계속 유지)

```bash
rviz2 --ros-args \
  -r /initialpose:=/robot11/initialpose \
  -r /tf:=/robot11/tf \
  -r /tf_static:=/robot11/tf_static
```

Fixed Frame=`map`, Map=`/robot11/map`(Transient Local), LaserScan=`/robot11/scan`.
아래 5번에서 언도킹한 뒤 **현재 실제 위치와 방향**을 2D Pose Estimate로 지정합니다.
라이다 점들이 지도 벽과 겹치는지 확인합니다. 경로 첫 목표를 초기 위치로 넣지 않습니다.

### 5번 — 언도킹과 확인

```bash
timeout 10s ros2 topic echo /robot11/dock_status --once
# is_docked=true일 때만 실행:
ros2 action send_goal /robot11/undock irobot_create_msgs/action/Undock '{}' --feedback

timeout 10s ros2 topic echo /robot11/scan --once \
  --qos-reliability best_effort --field header
```

언도킹 성공, scan 수신, RViz 위치 정렬 후 4번을 시작합니다.

### 4번 — Nav2 (계속 유지)

```bash
ros2 launch turtlebot4_navigation nav2.launch.py namespace:=/robot11 \
  params_file:="$PWD/scripts/robot11_agv/nav2_patrol.yaml"
```

### 5번 — 준비 확인 → 미리보기 → 순찰 시작

```bash
timeout 10s ros2 lifecycle get /robot11/amcl
timeout 10s ros2 lifecycle get /robot11/bt_navigator
timeout 10s ros2 lifecycle get /robot11/controller_server
timeout 10s ros2 lifecycle get /robot11/planner_server
python3 scripts/robot11_agv/patrol.py
```

네 노드 모두 `active [3]`, 실제 위치/방향 정렬, 라이다 수신이 확인되면:

```bash
python3 scripts/robot11_agv/patrol.py --execute --dwell 3
```

이 명령은 **28개 랙 순찰부터 최종 도킹까지** 수행합니다. 같은 시간에 route.py,
teleop, RViz 목표, 다른 mission client를 실행하지 않습니다. robot5는 공용 통로 밖에 둡니다.

랙마다 TURN_TO_TRAVEL(이동 방향 회전) → MOVE(점검 위치 이동) →
FACE_RACK(랙 방향 회전) → DWELL(3초 대기)를 순서대로 실행합니다.
이동은 NavigateToPose, 회전은 충돌 검사를 유지하는 Nav2 Spin 액션입니다.
현재 위치에서 목표까지 8cm 이내면 이동을 생략하고 랙 방향만 맞춥니다.
회전 차이가 8도 이내면 회전도 생략합니다. 별도 정밀 오차 검사로 중단하지 않습니다.
R01→R08, R15→R22는 동일 XY이므로 보통 방향만 바꿉니다.
4.4cm 간격의 끝쪽 랙에서는 작은 이동이 생략될 수 있습니다.

반드시 위 robot11 전용 nav2_patrol.yaml을 적용해 Nav2를 시작합니다.
이미 실행 중인 Nav2에는 파일 수정이 자동 반영되지 않으므로 정지 후 재시작합니다.
도착 허용값은 8cm/약 8도, 최대 전진 속도는 0.15m/s입니다.
짧은 이동에서 진행 실패가 너무 빨리 발생하지 않도록 진행 판정은 5cm/30초로 설정합니다.
실제 장애물 회피 궤적은 Nav2가 결정하며, 액션 실패는 순찰을 중단합니다.

랙마다 3초 대기하며 통과 지점에는 별도 3초 대기를 추가하지 않습니다.
실패/거절/시간초과/정차 중 Ctrl+C는 이후 목표와 도킹을 차단합니다.
Ctrl+C는 현재 액션 취소를 요청합니다. `STOP UNCONFIRMED`면 로봇 물리 정지를 사용합니다.
도킹 실패를 성공으로 처리하거나 자동 재시도하지 않습니다.

재실행은 중간 재개가 아닙니다. 다시 언도킹한 도크 앞에서 시작합니다.
종료는 로봇 정지 확인 후 4번 → 3번 → 2번 → 1번 순서로 종료합니다.

## 검증 범위

경로/28개 랙 순서/구역 간 출구/복귀 순서, 각 이동 단계 실패 차단,
정차 중단, 도킹 실패 처리, 언도킹 분기와 실패 차단의 자동 테스트를 통과했습니다.
미리보기와 Python 구문도 확인했습니다. 새 28개 랙 순찰과 자동 도킹은 실기 검증 전입니다.

## 현재 robot11 코드의 시작 방식

순찰 구역은 Z1 → Z2이며 28개 랙 방문 후 진입 통로를 통해 복귀합니다.
`racks.yaml`을 사용하고 `zones.yaml`은 읽지 않습니다.

처음 시작할 때 권장 순서:

1. Discovery, MAP-02 지도/AMCL, RViz를 실행합니다.
2. 도크 출구를 확보한 뒤 아래 명령으로 언도킹만 수행합니다.

```bash
python3 scripts/robot11_agv/patrol.py --execute --undock-only
```

3. 언도킹한 실제 위치와 방향을 RViz 2D Pose Estimate로 지정하고 scan 정합을 확인합니다.
4. robot11 Nav2를 시작합니다. 모든 관리 노드의 활성화 완료를 확인합니다.
5. 도크 앞에서 다음을 실행합니다.

```bash
python3 scripts/robot11_agv/patrol.py --execute --dwell 3
```

이미 언도킹되어 있으면 언도킹 액션을 반복하지 않습니다. 도킹 중에 위 순찰 명령을 직접
실행하면 자동 언도킹 후 준비 상태를 최대 180초 기다립니다. 이 시간 동안 측위를 맞추고
Nav2를 시작해야 합니다. 필요 시 `--ready-timeout 300`으로 준비 대기 시간을 지정합니다.
초기 pose는 코드가 자동으로 지정하지 않습니다.

출발 전 map_server, amcl 및 Nav2의 controller/smoother/planner/route/behavior/
velocity_smoother/collision_monitor/bt_navigator/waypoint_follower/docking_server 상태와
scan timestamp를 확인합니다. inactive나 센서 시간 오류가 있으면 준비 로그를 출력하며
기다리고, 제한 시간 초과 시 순찰 목표를 전송하지 않습니다. 이어 MAP-02 메타데이터,
최신 TF와 언도킹 상태, 도크로부터 0.8m 이내 시작 위치를 확인합니다.
이는 출발 전 검사이며 실행 중 TF/센서 문제의 근본 원인을 자동 복구하는 기능은 아닙니다.

`--execute` 없이 실행하면 이동 명령과 ROS 연결 없이 경로를 출력합니다.
카메라/도어/LED 검사는 아직 placeholder입니다. 실제 주행과 자동 도킹은 현장 검증이 필요합니다.

## dock_status QoS

robot11의 create3_repub는 RELIABLE / TRANSIENT_LOCAL로 도킹 상태를 보관합니다.
순찰 코드도 동일 QoS로 구독하여 시작 전에 발행된 마지막 상태를 받습니다.
상태 메시지는 주기 발행을 가정하지 않으며 수신 후 2초 만료 조건을 적용하지 않습니다.
scan과 TF의 시간 검사는 유지합니다. 언도킹 액션을 실행한 경우에는 SUCCEEDED,
액션 결과 is_docked=false 및 도킹 상태 false를 확인한 후 진행합니다.
보관된 도킹 상태만으로 현재 통신 연결이 정상이라는 뜻은 아닙니다.
