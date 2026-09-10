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
| 점검 pose 예외 (col 1) | x=3.229 클램프, yaw ±1.3072 (도어 중심 지향, 시선각 15.1°) — `oblique: true` |
| 벽 렌더 | 외벽 1셀. **중간 벽은 셀 경계 대칭 렌더로 2셀(0.10m @res 0.05, x 0.75~0.85)** — 개구부 y 범위·복도 폭에는 영향 없음 |
| 도크 | robot11 (0.27, 4.92, π) · robot5 (0.27, 0.33, π) |
| 통로 입구 | (1.40, 통로 y) |
| 개구부 | x=0.80 벽, y 2.40~3.20 |

`rack_id = "R" + aruco_id 2자리`, **R01이 오른쪽 벽 쪽**, row 1 = 도면 최상단 줄.

### col 1 점검 pose 클램프 (`oblique: true`)
col 1 랙(R01·R08·R15·R22·R29·R36·R43·R50)은 실물이 오른쪽 벽에 붙어 있어 랙 x 중심(3.395)에는
TB4(반경 0.171m)가 설 수 없습니다. `inspect_pose.x`를 `MAX_INSPECT_X = 3.50 − 0.171 − 0.05 = 3.279`로
클램프하고 yaw를 `atan2(도어중심 − pose)`로 도어 중심 지향(±1.3072 rad ≈ ±74.9°)으로 계산합니다.
- 카메라 광축은 여전히 도어 중심을 통과 — AC는 "카메라 광축이 도어 중심 ±3°" (v7 #55)
- 시선각 15.1° 비스듬, 도어까지 0.637m (수직일 때 0.615m). ArUco 판독 한계(60°) 대비 여유 충분
- 마진 10cm는 **지도 렌더 벽면 기준**(실물 3.495가 아니라 res 0.05 렌더 3.450) — costmap 마진이
  res 0.05에서 5cm, res 0.025에서 7.5cm로 AMCL 위치 오차(2~5cm)를 흡수합니다
- 나머지 48건은 종전과 동일(`oblique: false`, yaw ±π/2)

> **VERIFY 옆걸음 미러링 (MIS-05, v7 #56)**: 아래쪽 줄(yaw −π/2)에서 로봇 기준 왼쪽은 **+x = 벽 쪽**입니다.
> ```
> sidestep_x = inspect.x + 0.3 × (로봇 왼쪽 방향의 x 부호)
> if sidestep_x > MAX_INSPECT_X − 0.05 (= 3.179):  오른쪽 0.3m 이동 + 왼쪽 60° 회전 으로 미러링
> ```
> 아래쪽 줄 기준 col 1(3.529)·col 2(3.485)·col 3(3.275)이 미러링 대상, col 4(3.065)부터 정상.
> "왼쪽"이 로봇 기준인지 도어 힌지 기준인지는 R3·A1 확인 사항(힌지 기준이면 위·아래 줄에서 방향이 뒤집힘).

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
- **벽은 셀 경계에 맞춰 안쪽으로 렌더**됩니다 — 우측 벽 내면이 res 0.05에서 3.450, res 0.025에서 3.475
  (실물 3.495). `MAX_INSPECT_X = 3.229`는 이를 반영한 값으로, col 1 pose의 costmap 마진은
  res 0.05에서 0.050m · res 0.025에서 0.075m입니다. 기본은 **res 0.05**, 0.025 판은 AMCL 수렴이 나쁠 때 교체용.
- `initialpose` yaw π = quaternion `z=1.0, w=0.0`.
