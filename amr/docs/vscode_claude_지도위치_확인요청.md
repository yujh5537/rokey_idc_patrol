# 요청: 병합된 지도(/map) 위치가 로봇 TF 위치와 안 맞는 원인 확인

## 확인된 사실 (중요 — 방향을 헷갈리지 말 것)

- **로봇 TF는 정상입니다.** 로봇5, 로봇11 둘 다 world 좌표계 기준으로
  실제 물리적 위치와 정확히 일치하게 표시됨. 로봇5 도크가 world
  원점(0,0,0), 로봇11 도크가 그로부터 실측한 상대 위치로 정확히 뜸.
- **문제는 지도(/map)입니다.** map_merge가 발행하는 병합 지도의
  위치/좌표가, 위에서 확인한 정상적인 로봇 TF 위치와 어긋나 보임.
  즉 "로봇을 고치는 게 아니라 지도 쪽을 고쳐야 함."

## 시스템 구성 (참고)

- 로봇5 도크 = world 원점 (0,0,0)
- 로봇11 도크 = world 기준 (0, 4.58, yaw=0) — 실측값
- amr/config/map_merge_params.yaml 에 known_init_poses 방식으로
  이 좌표를 넣어서 multirobot_map_merge가 두 로봇의 개별 지도
  (/robot5/map, /robot11/map)를 병합해 /map으로 발행
- amr/launch/control_pc_full.launch.py 가 로봇마다 하나씩
  static_transform_publisher로 world -> robot5/map,
  world -> robot11/map TF를 발행 (로봇 표시용, 위 정상 결과의 근거)
- world_frame 설정은 "world"로 되어 있음

## 확인해주셨으면 하는 것

1. **map_merge_params.yaml의 init_pose_x/y/yaw 값**과,
   **실제 launch에서 static_transform_publisher에 넘겨지는
   robot11_y 값(또는 하드코딩된 값)**이 정확히 일치하는지 코드
   상에서 직접 비교 확인. (터미널에서 직접 비교하려 했으나
   grep 결과가 안 나와서 확인이 막힌 상태 — 파일 경로나 내용
   자체를 먼저 다시 확인해주세요.)

2. **multirobot_map_merge가 world_frame 설정을 어떻게 사용하는지**
   실제 소스코드(또는 설치된 패키지)를 열어서 확인해주세요.
   - map_merge가 각 로봇의 map->odom TF를 실시간으로 참조하는지,
     아니면 launch 시작 시점의 init_pose 파라미터만으로 고정된
     변환을 한 번 계산하고 그 이후로는 TF를 안 보는지
   - 만약 후자라면, 나중에(SLAM 드리프트 등으로) 로봇의 실제 TF
     위치가 조금씩 달라져도 map_merge의 병합 결과는 처음 계산한
     고정값 그대로 유지되어, 시간이 지날수록 로봇 TF와 지도가
     점점 벌어질 수 있다고 추정됨 — 맞는지 확인 필요

3. **/map 토픽의 origin이 실제로 어떻게 계산되는지**
   nav_msgs/OccupancyGrid의 info.origin 필드가 world 좌표계
   기준으로 정확히 어느 지점을 가리키는지, 그 계산 로직이
   init_pose 값과 실제로 정합한지 확인.

## 실행 중 직접 비교하려던 방법 (참고용, 필요시 재현)

```bash
# 지도 병합 파라미터 파일의 값
grep init_pose amr/config/map_merge_params.yaml

# 실제 발행 중인 TF의 값 (world -> robot11/map)
timeout 3 ros2 topic echo /tf_static

# 로봇11의 실제 TF 위치 (정상으로 확인됨, 비교 기준)
ros2 run tf2_ros tf2_echo world robot11/base_link

# 병합 지도의 origin
ros2 topic echo /map --field info --once
```

이 네 가지 값을 한 번에 뽑아서 서로 비교하는 스크립트를 만들어
직접 실행해서 확인해주시면 가장 정확할 것 같습니다.

## 최종 목표

로봇 TF(이미 정상)와 map_merge가 발행하는 /map의 좌표가
정확히 같은 world 좌표계 기준으로 일치하도록 원인을 찾아
고쳐주세요. 원인을 찾으면 어떤 값이 왜 어긋나 있었는지
간단히 설명해주세요.
