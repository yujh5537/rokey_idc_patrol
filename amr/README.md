# amr — 로봇5/로봇11 멀티로봇 SLAM + 실시간 지도 병합

관제 PC 1대에서 TurtleBot4 2대(robot5, robot11)의 SLAM 지도를 실시간 병합한다.

## 실행 순서

| 순서 | 어디서 | 명령 |
|---|---|---|
| 1 | 로봇5 PC | `ros2 launch amr/launch/robot_slam.launch.py namespace:=robot5 relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py` |
| 2 | 로봇11 PC | `ros2 launch amr/launch/robot_slam.launch.py namespace:=robot11 relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py` |
| 3 | 관제 PC | `ros2 launch amr/launch/control_pc_full.launch.py params_file:=$(pwd)/amr/config/map_merge_params.yaml rviz_config:=$(pwd)/amr/rviz/merged_map.rviz` |

- 두 로봇을 도크에 물린 상태에서 시작한다 (로봇5 도크 = world 원점, 로봇11 도크 = `(0, 4.58, 0)`).
- 3대 모두 `ROS_DOMAIN_ID` 동일하게.
- 병합 지도 자동 저장: 3번에 `save_map_script:=$(pwd)/amr/scripts/save_merged_map.py` 추가 →
  두 로봇이 언도킹 주행 후 다시 도킹을 완료하면 `amr/maps/merged_map.{pgm,yaml}` 저장.

## TF 프레임 접두사 문제 — 원인과 대응

### 원인

`turtlebot4_navigation/slam.launch.py` 를 `namespace:=/robot5` 로 띄우면

- **토픽**에는 네임스페이스가 붙는다: `/robot5/scan`, `/robot5/map`, `/robot5/tf` …
- **TF 프레임 이름**에는 안 붙는다: `map`, `odom`, `base_link`, `rplidar_link`

`slam.launch.py` 는 `slam.yaml` 의 `map_name`, `scan_topic` 만 치환하고
`odom_frame` / `map_frame` / `base_frame` 은 고정값 그대로 쓰기 때문이다
(slam_toolbox 에는 tf_prefix 파라미터가 없다). 로봇 베이스(create3 + rplidar)도
프레임 이름을 접두사 없이 발행한다.

→ 로봇5와 로봇11이 똑같은 프레임 이름(`odom`, `base_link`)을 써서 관제 PC 전역 TF
트리에서 구분 불가. rviz 에서 `Message Filter dropping message: frame 'rplidar_link'`
로 스캔이 계속 버려지는 것도 같은 원인(전역 트리엔 `robot5/rplidar_link` 만 있는데
`/robot5/scan` 메시지의 `frame_id` 는 `rplidar_link`).

### 현재 대응 (`tf_prefix_relay.py`)

로봇별로 `/<ns>/tf(_static)` 를 구독해 모든 프레임에 `<ns>/` 를 붙여 전역
`/tf(_static)` 로 재발행. 스캔도 `frame_id` 를 `<ns>/rplidar_link` 로 고쳐
`/<ns>/scan_ns` 로 재발행한다.

예전 문제와 해결:
- **중계 노드를 따로 켜야 했음** → `robot_slam.launch.py` 가 SLAM 과 한 묶음으로
  `respawn=true` 로 띄운다. 따로 켤 일 없음.
- **`world` 정렬이 자꾸 어긋남** → `world->odom` 을 걸지 않는다. slam_toolbox 는
  활성화 순간부터 `map->odom`(초기 identity)을 계속 발행하므로 `world->map` static
  하나만 있으면 트리가 이어진다. 예전엔 SLAM 시작 전후로 `world->odom` / `world->map`
  을 바꿔 걸어서 `odom` 의 부모가 둘이 되는 충돌이 났다. → `control_pc_full` 은
  `world->robotN/map` 만 건다.

### 근본 해결 (로봇 브링업 수정이 가능하면)

중계 자체를 없애려면 프레임을 **발행 시점**에 접두사화해야 한다. 로봇 하드웨어/브링업
쪽 작업이라 이 저장소 코드로는 안 되고, 각 로봇에서:

1. create3 웹 설정에서 `ROS_NAMESPACE` (또는 `tf_prefix`) 를 `robot5` 로 → `odom->base_link` 가 `robot5/odom->robot5/base_link` 로 발행됨
2. RPi 브링업의 `robot_state_publisher` 에 `frame_prefix:=robot5/`
3. rplidar 드라이버 `frame_id:=robot5/rplidar_link`
4. slam_toolbox 파라미터에 `odom_frame: robot5/odom`, `base_frame: robot5/base_link`, `map_frame: robot5/map`
5. 로봇 노드들의 `/tf`, `/tf_static` 를 네임스페이스로 remap 하지 말고 전역으로 발행

1~4가 모두 되면 `tf_prefix_relay` 없이 전역 `/tf` 가 바로 완성된다.

## 파일

| 파일 | 역할 |
|---|---|
| `launch/robot_slam.launch.py` | **로봇 PC용.** slam.launch.py include + tf_prefix_relay(respawn) |
| `launch/control_pc_full.launch.py` | **관제 PC용.** world 정렬 static + map_merge + rviz + (선택) 자동 언도킹/지도 저장 |
| `scripts/tf_prefix_relay.py` | `/<ns>/tf(_static)` → 전역 `/tf(_static)` 접두사 재발행, 스캔 `frame_id` 보정 |
| `scripts/save_merged_map.py` | 두 로봇 재도킹 시 병합 지도(`/map`) 저장 |
| `scripts/auto_undock.py` | 두 로봇 map 토픽 확인 후 동시 언도킹 |
| `scripts/robot5_path.py` | 로봇5 지그재그 스캔 경로 주행 (독립 스크립트) |
| `config/map_merge_params.yaml` | multirobot_map_merge 파라미터 (known_init_poses) |
| `config/nav2_robot5.yaml` | 로봇5 nav2 파라미터 |
| `rviz/merged_map.rviz` | 관제 PC rviz 설정 (LaserScan 은 `/robot5/scan_ns` 구독) |

> 탐사/병합 지도(`.pgm`, `.yaml`) 는 커밋 금지 (협업 규칙 5). `amr/maps/` 산출물은 드라이브로 공유.
