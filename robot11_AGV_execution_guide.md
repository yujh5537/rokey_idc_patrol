# robot11 좌표 주행 실행 안내

사용자가 이번 세션에서 주행 성공을 확인한 구성을 다시 실행하기 위한 안내서다. 모든 기본 명령은 PC3 `mu-02`에서 실행한다. 로봇 SSH 접속은 장애 진단 때만 사용한다.

## 실행 기준

- 저장소: https://github.com/yujh5537/rokey_idc_patrol
- 브랜치: `euiseok/20260909-agv-robot11-z4-route`
- 구현 커밋: `869014f23299603aa97b85c9184a00e78d6d2df5`
- 기반 main: `53fded2768bca365723d7635823a16f95186ff16`
- 스크립트: `scripts/robot11_agv/route.py`
- 지도: `src/idc_bringup/maps/idc_testbed.yaml` (MAP-02)
- ROS 2 Jazzy, ROS_DOMAIN_ID=2, robot11

이번 세션에서는 스캔 미수신·map TF 부재 상태에서 Nav2가 일부 inactive였고, 언도킹 후 스캔 수신과 map TF가 확인됐다. 이후 Nav2만 재시작하여 세 노드 모두 active가 됐으며 사용자가 주행 성공을 보고했다. 따라서 다음 실행에서는 언도킹·스캔·측위를 먼저 확인하고 Nav2를 실행한다. 이 기록은 모든 실패·취소 상황까지 실기 검증했다는 의미는 아니다.

## 목표 좌표

단위 m, 방향 rad, 프레임 map. 이 좌표는 현재 위치 출력이 아니라 이동 목적지다.

| 순서 | 이름 | x | y | 도착 yaw | 도착 후 |
|---|---|---:|---:|---:|---|
| 1 | 두 초기 위치의 중점 | 0.270 | 2.625 | -1.5708 (아래쪽) | 2초 대기 |
| 2 | Z2·Z3 통로 입구의 중점 | 1.400 | 2.800 | 0 (오른쪽) | 2초 대기 |
| 3 | Z4 통로 입구 | 1.400 | 0.700 | 0 (오른쪽) | 2초 대기 후 종료 |

Nav2가 장애물을 고려해 지점 사이 경로를 계획한다. 직선 주행을 강제하지 않는다. 자동 랙 검사·자동 도크 복귀는 포함하지 않는다. 다른 지도 `Final.yaml`로 바꾸면 동일한 map 좌표인지 확인하거나 좌표를 변환해야 한다.

## 터미널 배치와 실제 실행 순서

| 터미널 | 역할 | 실행 시점 | 유지 여부 |
|---|---|---|---|
| 1 | Discovery Server | 가장 먼저 | 주행이 끝날 때까지 유지 |
| 2 | 지도·AMCL | robot11 토픽 발견 후 | 유지 |
| 3 | RViz | AMCL 실행 후 | 관찰용으로 유지 |
| 4 | Nav2 | 언도킹·스캔·측위 확인 후 | 유지 |
| 5 | 상태 확인·언도킹·route.py | 각 단계에서 사용 | 명령 완료 후 재사용 |

실제 순서: **1 → 2 → 3 → 5에서 언도킹·측위 확인 → 4 → 5에서 주행**.

## 0 준비

로봇과 PC3가 기존 로봇 네트워크에 연결돼 있어야 한다. robot5는 경로 밖에 정지시키고 robot11에 다른 미션·teleop 목표를 보내지 않는다. 다른 PC에서 robot11의 SLAM·AMCL·Nav2를 중복 실행하지 않는다.

이미 받은 코드라면 매번 clone·설치·빌드를 반복하지 않아도 된다. 실행할 브랜치만 확인한다.

```bash
cd ~/collaboration/rokey_idc_patrol
git branch --show-current
git status --short
```

다른 브랜치에 있다면 수정 파일을 보관한 뒤 다음을 실행한다. 미커밋 작업을 강제로 버리지 않는다.

```bash
git switch euiseok/20260909-agv-robot11-z4-route
```

새 PC에서 처음 브랜치를 받을 때만:

```bash
git fetch origin
git switch --track origin/euiseok/20260909-agv-robot11-z4-route
```

지도 패키지가 아직 빌드되지 않았을 때만:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select idc_bringup
source install/setup.bash
```

## 1 터미널 1에서 Discovery Server

```bash
source /opt/ros/jazzy/setup.bash
ss -lunp | grep ':11811'
```

기존 Discovery Server가 사용 중이면 추가로 실행하지 않는다. 출력이 없으면:

```bash
unset ROS_DISCOVERY_SERVER
fastdds discovery --server-id 0
```

`Server is running`을 확인하고 창을 켜 둔다. **unset은 터미널 1에서만 실행**한다.

## 2 터미널 2에서 지도와 AMCL

아래 준비 블록은 터미널 2·3·4·5를 새로 열 때 각각 실행한다. 기존 `.bashrc`의 정상 동작하던 Discovery 설정을 유지한다.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/collaboration/rokey_idc_patrol
source install/setup.bash
export ROS_DOMAIN_ID=2
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

터미널 2에서 통신 확인:

```bash
echo "$ROS_DISCOVERY_SERVER"
ros2 topic list | grep robot11
```

`/robot11/scan`, `/robot11/odom` 등이 발견되면 진행한다. 토픽이 안 보이면 통신 문제를 먼저 해결한다. 토픽 이름이 보이는 것만으로 실제 데이터 수신이 증명되는 것은 아니다.

```bash
ls -lh "$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml"

ros2 launch turtlebot4_navigation localization.launch.py \
  namespace:=/robot11 \
  map:=$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
```

`Please set the initial pose`가 나오면 초기 위치 입력 전 대기 상태다. 창을 켜 두고 다음 단계로 간다.

## 3 터미널 3에서 RViz

2번의 준비 블록을 이 터미널에서도 실행한 뒤:

```bash
rviz2 --ros-args \
  -r /initialpose:=/robot11/initialpose \
  -r /tf:=/robot11/tf \
  -r /tf_static:=/robot11/tf_static
```

RViz 설정:

1. Global Options → Fixed Frame: `map`
2. Add → By topic → `/robot11/map` → Map
3. Map Durability Policy: `Transient Local`
4. Add → By topic → `/robot11/scan` → LaserScan
5. 이번 세션 스캔 발행자는 Reliable이었다. RViz Reliable 구독과 호환된다. 토픽만 보이는데 메시지 0건이면 도킹 상태·실제 라이다 회전부터 확인한다.

실제 로봇 위치를 알고 있다면 2D Pose Estimate로 지정할 수 있다. 단, 언도킹 전에 설정한 뒤 실제 센서 수신이 없었다면 언도킹 후 현재 위치를 다시 확인한다.

## 4 터미널 5에서 언도킹과 센서 확인

2번의 준비 블록을 이 터미널에서도 실행한다.

```bash
timeout 10s ros2 topic echo /robot11/dock_status --once
```

`is_docked: true`이거나 실제 도크에 접촉한 상태라면, 빠져나올 공간을 확보하고:

```bash
ros2 action send_goal /robot11/undock \
  irobot_create_msgs/action/Undock '{}' --feedback
```

`SUCCEEDED`, `is_docked: false`를 확인한다. 이미 언도킹한 상태면 반복할 필요 없다. timeout 명령으로 이동 Action을 끊어 정지시키려 하지 않는다.

라이다가 회전하는지 확인하고:

```bash
timeout 10s ros2 topic echo /robot11/scan --once \
  --qos-reliability best_effort --field header
```

header의 stamp·frame_id가 출력되고 RViz 스캔 메시지 수가 증가해야 한다.

## 5 RViz에서 현재 위치 확정

**언도킹 후 실제 위치·방향**을 기준으로 설정한다.

1. 2D Pose Estimate 클릭.
2. 지도에서 실제 robot11 중심 위치를 클릭.
3. 누른 채 실제 로봇 전면 방향으로 드래그한 뒤 놓기.
4. 스캔 점들이 지도 벽·랙에 겹치는지 확인.

도크 초기값 `(0.270,4.920,π)`는 로봇이 실제로 그 위치에서 왼쪽을 볼 때만 해당한다. 이전 실행에서 클릭한 `(0.392,5.127,0)`도 매번 재사용할 고정 초기값이 아니다. 초기 위치 설정은 이동 명령이 아니며, 부정확한 위치 입력을 센서 검증 대신 사용하면 안 된다.

터미널 5에서:

```bash
timeout 10s ros2 lifecycle get /robot11/map_server
timeout 10s ros2 lifecycle get /robot11/amcl

timeout 10s ros2 topic echo /robot11/amcl_pose --once \
  --qos-durability transient_local \
  --qos-reliability reliable
```

두 노드가 `active [3]`, 위치 출력 존재, RViz Global Status와 LaserScan Transform이 OK인지 확인한다. 현재 입력한 위치와 스캔 정합도 확인한 뒤 Nav2를 실행한다.

## 6 터미널 4에서 Nav2

2번의 준비 블록을 이 터미널에서도 실행한 뒤:

```bash
ros2 launch turtlebot4_navigation nav2.launch.py \
  namespace:=/robot11
```

창을 켜 둔다. 터미널 5에서 시작 완료 확인:

```bash
timeout 10s ros2 lifecycle get /robot11/bt_navigator
timeout 10s ros2 lifecycle get /robot11/controller_server
timeout 10s ros2 lifecycle get /robot11/planner_server
```

셋 모두 `active [3]`이어야 한다.

이번과 같이 Nav2를 센서·TF 준비 전에 켜서 일부 inactive가 남았다면, 준비 완료 후 **터미널 4만 Ctrl+C로 종료하고 같은 Nav2 명령으로 다시 실행**한다. Discovery·AMCL·RViz는 유지한다. 그래도 inactive면 반복 재시작하거나 강제 활성화하지 말고 새 실행의 첫 ERROR와 주변 로그를 확인한다.

## 7 터미널 5에서 경로 주행

좌표 미리보기 — 로봇 이동 없음:

```bash
python3 scripts/robot11_agv/route.py
```

모든 준비가 완료된 뒤 실제 이동:

```bash
python3 scripts/robot11_agv/route.py --execute
```

정상 로그 순서:

```text
GO dock_midpoint
ARRIVED dock_midpoint
GO z2_z3_midpoint
ARRIVED z2_z3_midpoint
GO z4_entry
ARRIVED z4_entry
ROUTE COMPLETE: stopped at Z4.
```

각 ARRIVED 후 기본 2초 대기한다. 목표 성공은 Nav2의 도착 허용 오차 기준이며 수학적으로 오차 0이라는 뜻은 아니다.

시간을 바꿀 때만 다음처럼 실행한다:

```bash
python3 scripts/robot11_agv/route.py --execute --dwell 3 --goal-timeout 240
```

기본 목표당 제한은 180초다. 실패·거부·취소 시 다음 목표로 넘어가지 않는다.

## 8 중단과 정상 종료

- 주행 중 중단: **터미널 5에서 Ctrl+C**. 현재 목표 취소를 요청한다.
- `STOP UNCONFIRMED` 또는 `Goal acceptance unknown`이면 물리 정지 버튼으로 멈추고 목표 상태를 확인한다. 창을 닫는 것만으로 정지를 보장하지 않는다.
- 정상 완료는 Z4에서 종료하며 자동으로 도크에 돌아가지 않는다.
- 전체 종료: 실제 정지 확인 → 터미널 4 Nav2 종료 → 터미널 3 RViz 종료 → 터미널 2 AMCL 종료 → 터미널 1 Discovery 종료.
- 다른 로봇·팀원이 Discovery를 사용 중이면 Discovery는 유지한다.

## 9 다음 실행 때 무엇을 반복할까

| 상황 | 필요한 작업 |
|---|---|
| 모든 터미널 종료 후 다시 시작 | 1~7번 실행 |
| 1~4번 터미널이 정상 실행 중 | 5번에서 상태·위치 확인 후 route 재실행 |
| 로봇만 재부팅 | 토픽·언도킹·스캔·초기 위치·Nav2 상태 재확인 |
| 로봇을 손으로 옮김 | 실제 위치로 2D Pose Estimate 재설정·스캔 정합 확인 |
| 지도 파일 변경 | 기존 목표 좌표와 새 지도 좌표계 정합 확인 |
| route 실패 후 재실행 | 정지·현재 위치·원인 확인 후 실행. 항상 첫 목표부터 다시 시작 |

Z4에서 그대로 다시 실행하면 **현재 위치에서 첫 목표 `(0.270,2.625)`로 이동**한다. 처음 출발 위치로 자동 복원하지 않으며, 초기 위치를 도크 좌표로 덮어써도 로봇이 도크로 이동하는 것이 아니다.

## 10 증상별 확인

| 증상 | 먼저 확인할 것 |
|---|---|
| `/robot11/amcl` Node not found | 터미널 2 실행 여부·Discovery 환경 |
| `Please set the initial pose` | 현재 실제 위치로 2D Pose Estimate |
| scan 토픽은 있지만 수신 0건 | 도킹 상태·라이다 회전·실제 header 수신 |
| `Frame [map] does not exist` | 스캔 수신과 AMCL의 TF 생성 |
| Nav2 일부 inactive | 센서·TF 준비 후 터미널 4만 재시작 |
| TF extrapolation 경고가 계속 발생 | PC3·로봇 시간 동기화와 TF 지연 확인. 초기 pose 반복 입력으로 덮지 않기 |
| `Waiting for an action server` | 해당 Action 서버 발견·실행 상태 확인 |
| 경로 계산 실패 | 현재 위치·목표 주변 장애물·costmap과 지도 확인 |

SSH 진단이 필요한 경우에만 PC3 새 터미널에서:

```bash
ssh ubuntu@192.168.107.111
```

프롬프트가 `ubuntu@turtlebot4`로 바뀌어야 로봇 내부다. `mu-02@mu-02`는 PC3다. 로봇 내부에서도 ROS 환경이 서비스와 일치하는지 확인해야 하며, SSH에서 토픽이 안 보인다는 사실만으로 센서 고장을 단정하지 않는다.
