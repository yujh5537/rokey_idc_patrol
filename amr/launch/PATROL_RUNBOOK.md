# 순찰 통합 실행 절차 (Phase 1 지도 제작 → Phase 2 순찰)

- **PC1** = robot5 담당, **PC2** = robot11 담당, **관제 PC** = localization·Nav2·순찰 실행
- 순찰은 SLAM 결과가 아니라 정적 지도 `src/idc_bringup/maps/idc_testbed.yaml`(MAP-02)를 쓴다.
  Phase 1 이 만드는 병합 지도는 `amr/maps/` 에 저장만 되고 Phase 2 는 쓰지 않는다.

## 공통 — 모든 PC, 새 터미널마다

```bash
source /opt/ros/jazzy/setup.bash
source ~/turtlebot4_ws/install/setup.bash
cd ~/rokey_idc_patrol && source install/setup.bash
export ROS_DOMAIN_ID=2 ROS_SUPER_CLIENT=True \
  ROS_DISCOVERY_SERVER=";;;;;192.168.107.105:11811;;;;;;192.168.107.111:11811;"
ros2 topic list | grep -E "robot5|robot11" | head -3   # 통신 확인 (안 나오면 R1)
```

---

## PHASE 1 — 지도 제작 (SLAM + world 정렬 병합)

두 로봇을 도크에 문 상태에서 시작.

### PC1 (robot5)
```bash
ros2 launch amr/launch/robot_slam.launch.py namespace:=robot5 \
  relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py
# 새 터미널 — 텔레옵
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/robot5/cmd_vel
```

### PC2 (robot11)
```bash
ros2 launch amr/launch/robot_slam.launch.py namespace:=robot11 \
  relay_script:=$(pwd)/amr/scripts/tf_prefix_relay.py
# 새 터미널 — 텔레옵
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/robot11/cmd_vel
```

### 관제 PC
```bash
ros2 launch amr/launch/control_pc_full.launch.py \
  merge_script:=$(pwd)/amr/scripts/merge_maps_world.py \
  rviz_config:=$(pwd)/amr/rviz/merged_map.rviz \
  save_map_script:=$(pwd)/amr/scripts/save_merged_map.py
```
→ 텔레옵으로 두 구역 매핑 → 두 로봇 **재도킹** → `save_merged_map.py` 가
`amr/maps/merged_map.{pgm,yaml}` 저장.

### Phase 1 종료
- PC1·PC2: `robot_slam.launch.py` **Ctrl+C**
- 관제 PC: `control_pc_full.launch.py` **Ctrl+C** (world→map static TF·map_merge 가
  Phase 2 의 AMCL 과 충돌하므로 반드시 종료)
- 두 로봇 도킹 상태 확인

---

## PHASE 2 — 순찰

### PC1, PC2
**실행할 것 없음.** 로봇 자체 bringup(create3 + rplidar)이 `/robotN/tf`, `/robotN/scan`,
`/robotN/dock_status` 를 계속 발행하면 된다. 로봇 언도킹 물리 보조만.
(`/robotN/tf` 가 안 보이면 Phase 1 의 `tf_prefix_relay` 를 해당 PC 에서 계속 띄워 둔다.)

### 관제 PC — 터미널 A : bringup (유지)
```bash
ros2 launch amr/launch/patrol_bringup.launch.py
```
robot5·robot11 각각 localization(AMCL + MAP-02 map_server) + Nav2 + RViz 2개.

### 관제 PC — 수동 단계
1. lifecycle 확인 — 모두 `active [3]`:
   ```bash
   for n in amcl bt_navigator controller_server planner_server; do
     ros2 lifecycle get /robot5/$n; ros2 lifecycle get /robot11/$n
   done
   ```
2. 두 로봇 언도킹 (robot5 스크립트는 스스로 언도킹하지 않음 → 필수):
   ```bash
   ros2 action send_goal /robot5/undock  irobot_create_msgs/action/Undock "{}"
   ros2 action send_goal /robot11/undock irobot_create_msgs/action/Undock "{}"
   ```
3. RViz(robot5), RViz(robot11) 각각:
   - Global Options → Fixed Frame = `map`
   - Add → Map : Topic `/robot5/map` (또는 `/robot11/map`), Durability **Transient Local**
   - Add → LaserScan : Topic `/robot5/scan` (또는 `/robot11/scan`)
   - **2D Pose Estimate** 로 언도킹한 실제 위치·방향 지정 → 라이다 점이 지도 벽과 겹치는지 확인

### 관제 PC — 터미널 B : 순찰 시작
```bash
ros2 launch amr/launch/patrol_start.launch.py
```
- `robot5` 즉시 출발 → **5초 뒤** `robot11` 출발
- 각 로봇 28개 랙 순찰(랙마다 3초 대기) 후 자동 도킹
- 옵션: `lead_delay:=10.0` · `lead:=robot11` · `dwell:=5.0`
  · `venv_activate:=$HOME/venvs/rokey_venv/bin/activate`

두 스크립트는 출발 전 MAP-02 규격 / 최신 TF / 언도킹 상태 / 도크 0.8 m 이내를 검사하고
하나라도 아니면 아무 목표도 보내지 않는다.

### 중단 / 종료
- 순찰 중단: 터미널 B **Ctrl+C** (현재 액션 취소, 이후 목표·도킹 차단)
- 전체 종료: 터미널 B → 터미널 A **Ctrl+C**
- 재실행은 중간 재개가 아니다. 다시 도크 앞에서 언도킹부터.

---

## 속도

robot5·robot11 은 `amr/scripts/robotN_agv/nav2_patrol.yaml` 로 Nav2 를 띄우며 두 파일의
속도 파라미터는 동일하다 (전진 0.15 m/s, 회전 1.0 rad/s, 도착 허용 8 cm / 8°).
