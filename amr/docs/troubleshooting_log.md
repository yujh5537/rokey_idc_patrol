# 오늘 겪은 시행착오 기록 (VS Code Claude Code 전달용)

이 파일은 claude.ai에서 로봇5·로봇11 지도 병합 시스템을 구축하며
오늘 실제로 겪은 문제와 해결 과정을 정리한 것입니다.
작업 시작 전에 이 파일을 먼저 읽고, 같은 실수를 반복하지 않도록
참고해주세요.

---

## 1. TF 프레임 이름 충돌 (가장 근본적인 문제)

**증상**: 로봇5, 로봇11 둘 다 SLAM을 켜면 rviz에서 로봇 모델이 원점에
겹쳐 보이거나 아예 안 뜸.

**원인**: `turtlebot4_navigation`의 slam.launch.py를
`namespace:=/robot5`로 실행해도, 토픽 이름(`/robot5/scan` 등)에는
접두사가 붙지만 **TF 프레임 이름(`odom`, `base_link`, `map`)에는
붙지 않음.** slam.yaml 설정에 다음과 같이 고정 문자열로 박혀 있음:
```yaml
odom_frame: odom
map_frame: map
base_frame: base_link
```

**시도했다가 실패한 것**:
- slam_toolbox에 `tf_prefix` 파라미터가 있는지 확인 →
  `ros2 param describe /robot5/slam_toolbox tf_prefix` 결과
  "해당 파라미터 없음" — 이 버전엔 그런 파라미터 자체가 없었음
- slam.yaml을 복사해서 `odom_frame: robot5/odom` 식으로 직접
  수정한 커스텀 파라미터 파일로 실행 → RobotModel의 몸체 일부가
  사라지고 더 나빠짐 (URDF/robot_state_publisher는 여전히 접두사
  없는 `base_link`를 쓰는데 slam_toolbox만 접두사 붙은 이름을
  찾게 돼서 서로 안 맞음)

**최종 임시 해결책**: `tf_prefix_relay.py`라는 중계 노드를 직접
작성. 로봇의 `/robot5/tf`, `/robot5/tf_static`을 구독해서 이름
앞에 "robot5/"를 붙여 전역 `/tf`, `/tf_static`으로 재발행.
로봇11도 `--ns robot11`로 별도 프로세스 실행.

이건 **근본 해결이 아니라 우회책**입니다. 이 중계 노드가 안 켜져
있으면 문제가 그대로 재발합니다.

---

## 2. odom→map 전환 시점 문제

**증상**: `world → robot5/odom`으로 static_transform을 걸어두면
처음엔 잘 되다가, 로봇이 언도킹해서 움직이기 시작하면 갑자기
"두 개의 연결 안 된 나무" 에러가 남.

**원인**: SLAM이 실제로 지도를 만들기 시작하면
`robot5/odom`의 부모가 자동으로 `robot5/map`으로 바뀜.
미리 만들어둔 `world → robot5/odom` 다리는 그대로 남아있는데,
이제 실제 TF 트리는 `world`가 아니라 `robot5/map`을 통해서만
연결되므로 두 나무로 쪼개짐.

**해결**: 로봇이 도크에 정지해 있을 때는 `world → robotN/odom`,
언도킹해서 SLAM이 map을 만들기 시작하면 `world → robotN/map`으로
static_transform을 갈아 끼워야 함. 또는 처음부터 `world → robotN/map`으로
걸어두면 (도크 상태에서는 반대편이 아직 없어 경고만 뜨고, 움직이기
시작하면 자동으로 이어짐) 재작업 없이 넘어갈 수 있음.

---

## 3. odom 드리프트 (도크 위치와 소프트웨어 원점 불일치)

**증상**: 로봇이 도크에 물려 있는데 `world` 기준 위치를 재보면
(0,0,0)이 아니라 엉뚱한 값이 나옴.

**원인**: odom 좌표계의 원점(0,0,0)은 "로봇이 처음 켜진 순간의
위치"로 고정됨. 로봇이 도킹 안 된 상태에서 이미 켜져 있었다면,
그 이후 도크에 다시 물려도 소프트웨어상 원점은 그대로 예전 위치.

**해결**: 로봇을 도크에 정확히 물린 상태에서 재부팅(전원 껐다 켬).
그 순간이 새로운 odom 원점이 되어 실측한 도크 좌표와 일치하게 됨.

---

## 4. 시간 동기화 미설치로 인한 스캔 유실

**증상**: `Message Filter dropping message: frame 'rplidar_link'
... discarding message because the queue is full` 경고가 계속 뜨고
지도가 안 자람.

**원인**: 관제PC에 `chrony`(시간 동기화 도구)가 설치되어 있지
않아서, PC 시계가 로봇 시계와 최대 70초까지 벌어져 있었음.
스캔 데이터의 타임스탬프가 TF 버퍼 기준보다 과거로 판정되어
계속 버려짐.

**해결**:
```bash
sudo apt install chrony -y
chronyc tracking   # 확인
sudo chronyc makestep   # 강제로 즉시 맞춤
```
로봇 쪽은 이미 chrony가 정상 동작 중이었고, 관제PC만 문제였음.
**새 PC에서 작업을 시작할 때마다 이 설치 여부부터 확인 필요.**

---

## 5. 관제PC 부하 — SLAM 2대 동시 실행

**증상**: 로봇5, 로봇11 SLAM을 관제PC 한 대에서 동시에 실행하면
CPU/네트워크 부하로 스캔이 계속 버려짐. map_merge 노드가
segfault(exit code -11)로 죽기도 함.

**해결**: SLAM 계산은 PC1(robot5 담당), PC2(robot11 담당)로
분산 실행. 관제PC는 map_merge, tf_prefix_relay, rviz만 담당.
같은 `ROS_DOMAIN_ID`에 있으면 다른 PC에서 실행한 노드의
토픽도 그대로 구독 가능.

---

## 6. map_saver 저장 실패

**증상**: `ros2 run nav2_map_server map_saver_cli -f 이름
--ros-args -r __ns:=/robot5` 실행 시 정확히 2초 후
`Failed to spin map subscription` 에러.

**원인**: `-r __ns:=/robot5` 방식은 `/robot5/map`이 아니라
`/map`을 구독하려 시도함. 토픽 이름이 실제와 달라서 기본
타임아웃(2초) 안에 못 받고 실패.

**해결**: `-t` 옵션으로 토픽을 직접 지정하고 타임아웃 연장.
```bash
ros2 run nav2_map_server map_saver_cli \
  -t /robot5/map -f robot5_map \
  --ros-args -p save_map_timeout:=10.0
```
더 확실한 대안: `slam_toolbox`의 `save_map` 서비스를 직접 호출.

---

## 7. Discovery Server 로봇 교체 시 재설정 누락

**증상**: 로봇이 robot2에서 robot11로 교체됐는데, 통신이 하나도 안 잡힘.

**원인**: `/etc/turtlebot4_discovery/setup.bash`의
`ROS_DISCOVERY_SERVER` 문자열에서 세미콜론 위치가 Server ID를
의미하는데, 새 로봇의 정확한 ID·IP로 재등록을 안 함.

**해결**: `configure_discovery.sh` 스크립트로 재설정. 여러 로봇
등록 시 중간에 "add another(a)"를 선택해야 하는데, 실수로 첫
번째 입력 후 "done(d)"을 눌러서 두 번째 로봇이 누락됐던 적 있음.

---

## 현재 확정된 좌표 기준

- world 원점(0,0,0) = 로봇5 도크
- 로봇11 도크 = world 기준 (0, 4.58, y축은 로봇 기준 오른쪽 방향)
- 좌표축 정의: x축 = 로봇 후면 방향, y축 = 로봇 오른쪽 방향
  (초기에는 x=정면, y=왼쪽이었다가 중간에 180도 회전하는 것으로
  변경됨 — 혹시 이전 기록에 옛 정의가 남아있다면 이게 최신 기준)

## 현재 파일 구조

```
amr/
├── README.md                          (구조·원인·근본해결 경로 문서)
├── launch/
│   ├── robot_slam.launch.py           (로봇 PC용: SLAM + tf_prefix_relay 한 묶음, respawn)
│   └── control_pc_full.launch.py      (관제 PC용: world 정렬 + map_merge + rviz + 저장/언도킹)
├── config/map_merge_params.yaml
├── config/nav2_robot5.yaml
├── rviz/merged_map.rviz               (LaserScan 은 /robot5/scan_ns 구독)
└── scripts/
    ├── tf_prefix_relay.py    (TF 이름 접두사 중계 + 스캔 frame_id 보정 → /<ns>/scan_ns)
    ├── save_merged_map.py    (두 로봇 재도킹 시 /map 저장, map_saver 는 -t 옵션 사용)
    ├── auto_undock.py        (map 토픽 확인 후 조건부 자동 언도킹)
    └── robot5_path.py        (시간 기반 이동, TF/Nav2 불필요)
```

---

## 2026-09-10 launch 구조 개편 (VS Code Claude Code)

이 로그의 #1·#2·#5 결론을 코드에 반영:

- **#5 (관제 PC 부하)** → SLAM 을 `robot_slam.launch.py` 로 분리. 로봇 PC 1대당
  `ros2 launch amr/launch/robot_slam.launch.py namespace:=robot5 relay_script:=.../tf_prefix_relay.py`.
  `control_pc_full.launch.py` 에서는 SLAM 제거.
- **#1 (중계 노드 따로 켜야 함)** → `robot_slam.launch.py` 가 SLAM 과 `tf_prefix_relay` 를
  한 묶음으로 `respawn=true` 실행. 따로 켤 일 없음. (근본 해결은 README "근본 해결" 참고 —
  Create3 네임스페이스 + robot_state_publisher frame_prefix + rplidar frame_id)
- **#2 (world→odom / world→map 전환)** → `control_pc_full` 은 `world→robotN/map` 만 건다.
  slam_toolbox 가 활성화 즉시 `map→odom`(초기 identity)을 발행하므로 전환 불필요.
- **#4 (스캔 유실)** → 여전히 유효. 새 PC / 로봇 교체 시 `chronyc tracking` 으로
  로봇↔관제 PC 시계 오차부터 확인. 한 PC 에서 SLAM 2개를 돌려도 (#5) 같은 증상이 난다.
- **#6 (map_saver)** → `save_merged_map.py` 는 `-t /map` 로 토픽 직접 지정.
- **좌표 불일치 (로봇이 자기 지도에서 회전/이동해 뜸)** → TF static(`world->robotN/map`)
  과 `map_merge` 의 `init_pose_*` 가 달라서 생긴다. `control_pc_full.launch.py` 가
  `r5_*/r11_*` 인자 하나로 둘 다 세팅하도록 통합 (map_merge yaml 은 RewrittenYaml 로 덮어씀).
  좌표계는 기본에서 x·y 를 180° 돌린 것 → `r5_yaw`/`r11_yaw` 기본값 π.

## 현재 확정된 좌표 기준 (재확인)

- world 원점 = 로봇5 도크, 로봇11 도크 = world (0, 4.58, 0)
- 좌표계 = 기본(정면 +x, 왼쪽 +y)에서 x·y 를 **180° 회전** → world 정렬 yaw = π
- 이 값은 `control_pc_full.launch.py` 의 `r5_*`, `r11_*` 인자로만 조정. 여러 곳에서
  따로 고치면 다시 어긋난다.
