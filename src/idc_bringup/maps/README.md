# MAP-02 — 실측 정적 지도 · racks.yaml (2026-09-09)

실측 도면 350×560cm + PM 확정 답변 7건을 파라미터화해 생성한 정적 지도와 랙 데이터.
**racks.yaml은 순찰 경로·rack_id·존·도크의 단일 기준(인터페이스 등급)** — 좌표를 바꿔야 하면
개별 수정하지 말고 `scripts/gen_static_map.py` 상단 파라미터를 고쳐 재생성한다.

## 파일 (`src/idc_bringup/`)
| 경로 | 내용 |
|---|---|
| `maps/idc_testbed.pgm` `maps/idc_testbed.yaml` | res 0.05 — Nav2·AMCL 기본. **우선 이걸 사용** |
| `maps/res_0.025/` | 정밀판 (랙 깊이 8.5cm ≈ 3.4셀). AMCL 수렴이 나쁘면 교체 |
| `maps/preview.png` | 랙 번호 · 순찰 경로 · 도크 미리보기 |
| `config/racks.yaml` | 랙 56기 점검 pose · 존 4 · 도크 2 · 순찰 순서 |
| `scripts/gen_static_map.py` | 생성기. `python3 gen_static_map.py --res 0.05 --out out/` |

## 좌표계
보드 좌하단 = (0,0), x 오른쪽 +, y 위쪽 +, m, yaw rad. 도면(위→아래) 값은 `y = 5.60 − y_top` 로 변환됨.
지도 origin은 (−0.5, −0.5) — 보드 바깥 0.5m는 unknown.

| 항목 | 값 (ROS map 프레임, m) |
|---|---|
| 통로 중심선 | Z1 y=4.90 · Z2 3.50 · Z3 2.10 · Z4 0.70 |
| 랙 x 중심 (col 1→7) | 3.395 / 3.185 / 2.975 / 2.765 / 2.555 / 2.345 / 2.135 |
| 점검 pose | 랙 x 중심, 통로 y, yaw +π/2(위쪽 줄) / −π/2(아래쪽 줄) |
| 도크 | robot11 (0.27, 4.92, π) · robot5 (0.27, 0.33, π) |
| 통로 입구 | (1.40, 통로 y) |
| 개구부 | x=0.80 벽, y 2.40~3.20 |

`rack_id = "R" + aruco_id 2자리`, **R01이 오른쪽 벽 쪽**, row 1 = 도면 최상단 줄.

## 사용
```bash
# [PC1 또는 PC2] 로봇별 측위 (초기 pose = racks.yaml docks[robot])
ros2 launch turtlebot4_navigation localization.launch.py namespace:=/robot11 \
  map:=$(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
ros2 launch turtlebot4_navigation nav2.launch.py namespace:=/robot11
# 초기 pose 발행 (robot11 도크: x 0.27 y 4.92 yaw π / robot5: x 0.27 y 0.33 yaw π)
ros2 topic pub --once /robot11/initialpose geometry_msgs/PoseWithCovarianceStamped \
  '{header:{frame_id: map}, pose:{pose:{position:{x: 0.27, y: 4.92}, orientation:{z: 1.0, w: 0.0}}}}'
```
- R2 `patrol_planner`: `patrol_routes[robot]` 순서 그대로 `inspect_pose`를 goal로. 통로 진입은 `zones[Z].entry_pose`.
- R3: 순찰 종료 후 `docks[robot]`으로 복귀(순차 도킹 없음).
- A3: SDD 4.2.6 `zones.yaml`은 이 파일에서 파생(존 폴리곤 = 통로 y ± 0.615).

## 첫 실기 검증 순서 (9/9)
1. rviz에서 `/map` 위에 LiDAR 스캔이 벽·랙 줄과 겹치는지 (AMCL 수렴)
2. `zones.Z1.entry_pose` (1.40, 4.90) 로 Nav2 goal 1회 → GATE-2 "goal 도달 1회"
3. `patrol_routes.robot11` 첫 3개(R07→R06→R05) `inspect_pose` 순차 goal → 정면 정렬·3초 정지 확인

## 트러블슈팅
- 스캔이 랙 줄과 어긋남 → 실물 오차(랙 위치·통로 폭). 수치를 주면 스크립트 상단 파라미터만 고쳐 재생성(5분).
- AMCL이 벽 0.5cm를 못 잡음 → `maps/res_0.025/` 로 교체.
- `initialpose` yaw π = quaternion `z=1.0, w=0.0`.
