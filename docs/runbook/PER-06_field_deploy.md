# PER-06 인식·이벤트 노드 현장 배치 런북

**작업 ID** PER-06 / UT-PC · **소요** PC당 약 15분

인식(YOLO·ArUco)·이벤트 판정 노드를 실제 PC에 올려 동작과 성능을 확인하는 절차입니다.
1차 실행에서 실패한 원인 6건을 반영했습니다(9장 이력 참조).

---

## 0. 무엇을 하는 작업인가

```
   robot5 카메라 ──▶ [PC1] YOLO(문 상태) + ArUco(랙 번호) ──▶ "R17, 열림" 초당 5회 이상
   robot11 카메라 ─▶ [PC2] 같은 일 (담당 로봇만)                 │
                                                                ▼
                                    [PC3] 이벤트 엔진 — 응시 구간 결과를 모아 확정 → 서버
```

- PC1은 `robot5`만, PC2는 `robot11`만 봅니다. **PC3는 영상을 구독하지 않습니다.**
- 학습된 문 인식 모델(`idc_door_v1.pt`)이 없는 동안에는 기본 가중치(`yolov8n.pt`)로 **속도·CPU만** 측정합니다.
  문 열림/닫힘이 안 잡히는 것은 정상이며, 마커(랙 번호) 인식은 정상 동작해야 합니다.

### 측정 항목

| 항목 | 기준 | 확인 위치 |
|---|---|---|
| objects Hz | ≥5 | `ros2 topic hz` |
| YOLO FPS | ≥5 | launch 터미널 로그 `YOLO FPS≈` |
| CPU 사용률 | ≤80% (PC3는 ≤50%) | `top` |

---

## 1. 공통 전제

| PC | IP | 담당 로봇 |
|---|---|---|
| PC1 | 192.168.107.132 | **robot5** |
| PC2 | 192.168.107.22 | **robot11** |
| PC3 | 192.168.107.21 | — |

WiFi `turtle07`. 시작 전 확인:

```bash
ros2 topic list | grep -E "robot5|robot11" | head -3
```

아무것도 안 나오면 `ros2 daemon stop && ros2 daemon start` 후 재시도.
그래도 안 나오면 네트워크 문제이며 인식 코드와 무관합니다 — AMR 담당(R1)에게 문의.

---

## 2. PC1 / PC2 — 인식 노드

PC1은 아래의 `robot5`를, PC2는 `robot11`을 사용합니다. 두 PC는 동시에 진행해도 됩니다.

### 2-1. 코드 받기

```bash
cd ~/idc_ws
git fetch --all
git checkout main && git pull
git log --oneline -1
```

> 인식 코드 PR이 main에 병합되기 전이라면 작업 브랜치를 직접 받습니다.
> 그 경우 PM이 브랜치명과 최소 커밋 해시를 알려 주며, `git log --oneline -1`이
> 그 해시 이상인지 확인해야 합니다. **옛 스텁이 실행되면 objects가 생기지 않습니다.**

### 2-2. 빌드

```bash
rm -rf build/idc_msgs install/idc_msgs build/idc_perception install/idc_perception
colcon build --packages-select idc_msgs idc_perception --symlink-install
source install/setup.bash
```

기대: `Summary: 2 packages finished`. `setuptools` 경고는 무시합니다.

> **왜 지우고 빌드하나** — 메시지 규격(`idc_msgs`)이 교체된 이력이 있습니다.
> 옛 산출물이 남아 있으면 빌드는 통과하는데 실행 때 "그런 필드 없음"으로 죽습니다.

### 2-3. 모델 파일

가중치는 레포에 커밋하지 않습니다. 공유 경로에서 받아 `~/idc_ws/models/`에 둡니다.

```bash
mkdir -p ~/idc_ws/models
cp <받은 경로>/yolov8n.pt ~/idc_ws/models/
ls ~/idc_ws/models/
```

### 2-4. 파이썬 환경 (venv)

```bash
ls -d ~/rokey_venv ~/venvs/rokey_venv 2>/dev/null     # 있는 경로 확인
source ~/rokey_venv/bin/activate                       # 위에서 나온 경로로
python3 -c "import rclpy, ultralytics, torch; print('OK', torch.cuda.is_available())"
```

기대: `OK True`

- `rclpy` 에러 → venv가 시스템 패키지를 못 봅니다(`--system-site-packages` 아님). 진행하지 말고 PM에게.
- `False` → GPU 미인식. `device:=cpu`로 진행하고 보고에 기록.

> **왜 필요한가** — YOLO가 쓰는 PyTorch가 시스템 파이썬이 아니라 venv에만 설치돼 있습니다.
> activate 없이 실행하면 yolo_node가 기동하지 못하고 **2초마다 죽었다 살아나기를 반복**합니다.

### 2-5. 기동

```bash
ros2 launch idc_perception perception.launch.py \
  namespace:=robot5 \
  model_path:=$HOME/idc_ws/models/yolov8n.pt \
  use_republish:=true device:=0
```

정상이면 다음 세 줄이 보입니다:

```
[yolo_node]:       yolo_node up: model=... device=0
[aruco_node]:      aruco_node up: DICT_5X5_250, id 1..56
[perception_node]: perception_node up: robot=robot5 racks=56 cx=352.0
```

`cx`는 카메라 폭의 절반이며 `camera_info`에서 자동으로 읽습니다(폭 704 → 352).
**이 터미널은 켜 둔 채로** 새 터미널을 엽니다.

#### launch 인자

| 인자 | 기본값 | 설명 |
|---|---|---|
| `namespace` | (필수) | `robot5` \| `robot11` |
| `model_path` | (필수) | `.pt` 절대 경로. 레포 밖 |
| `device` | `0` | CUDA 인덱스. GPU 없으면 `cpu` |
| `imgsz` | `640` | GPU 없고 FPS가 모자라면 `480` |
| `image_width` | `704` | `camera_info` 수신 전 폴백. 보통 건드릴 필요 없음 |
| `use_republish` | `true` | compressed→raw 변환 포함. 별도 republish가 이미 돌면 `false` |

### 2-6. 측정 (새 터미널)

```bash
cd ~/idc_ws && source install/setup.bash && source ~/rokey_venv/bin/activate

ros2 topic hz /robot5/perception/objects                      # objects Hz — 20초 관찰 후 Ctrl+C
nvidia-smi --query-gpu=utilization.gpu --format=csv -l 2      # GPU 실사용 확인 (Ctrl+C)
top -bn1 | head -15                                           # CPU
```

YOLO FPS는 2-5 터미널의 `YOLO FPS≈…` 줄에서 읽습니다.

### 2-7. 눈으로 확인 (가장 중요)

로봇을 랙 정면 약 60cm에 세우고:

```bash
ros2 run rqt_image_view rqt_image_view /robot5/perception/image_annotated
ros2 topic echo /robot5/perception/objects
```

`rack_id`로 나오는 번호가 **실제 그 랙에 붙은 마커 번호와 같아야 합니다.**
다르면 즉시 PM에게 — 시연에서 엉뚱한 랙이 보고됩니다.

`door_state: ""`, `confidence: 0.0`은 학습 모델이 없는 동안 정상입니다.

### 2-8. Nav2 동시 실행 (여유 있으면)

Nav2를 띄운 상태에서 `top`을 다시 측정합니다(UT-PC 기준 CPU ≤80%).
시간이 없으면 "단독 측정"으로 기록합니다.

---

## 3. PC3 — 이벤트 엔진

PC1·PC2가 떠 있어야 3-3부터 확인됩니다. 3-1·3-2는 미리 해 둘 수 있습니다.

### 3-1. 코드·빌드

```bash
cd ~/idc_ws && git fetch --all
git checkout main && git pull && git log --oneline -1
rm -rf build/idc_msgs install/idc_msgs build/idc_event install/idc_event
colcon build --packages-select idc_msgs idc_event --symlink-install
source install/setup.bash
```

### 3-2. 네트워크 환경 확인

```bash
echo "DOMAIN=$ROS_DOMAIN_ID"
echo "DISCOVERY=$ROS_DISCOVERY_SERVER"
echo "SUPER_CLIENT=$ROS_SUPER_CLIENT"
```

**PC1·PC2와 같아야 합니다.** 이 프로젝트는 로봇 2대가 각각 Discovery Server 역할을 하고
모든 PC가 두 대 모두에 등록하는 구성입니다(TurtleBot4 기본). PC3만 다르면 두 로봇 중
하나 또는 둘 다 못 봅니다. 다르면 R1에게.

### 3-3. PC1·PC2 데이터 도착 확인

```bash
ros2 topic hz /robot5/perception/objects /robot11/perception/objects
```

기대: 두 줄 다 `average rate: 5` 이상.
한쪽이 `no new messages`면 그 PC의 노드 기동 여부부터 확인하고, 떠 있다면 3-2 문제입니다.

### 3-4. 기동

```bash
ros2 launch idc_event event_engine.launch.py
```

기대: `event_engine up: robots=['robot5', 'robot11'] min_open_frames=10 open_ratio=0.6 ... racks=56`

### 3-5. 이벤트 확인 (새 터미널)

```bash
cd ~/idc_ws && source install/setup.bash
ros2 topic echo /event/events
```

미션 노드가 응시 신호(`MissionState`)를 주기 전에는 **아무것도 안 나오는 것이 정상**입니다.
이벤트는 로봇이 랙 앞에서 정지해 응시하는 구간에서만 판정됩니다.

수동으로 창을 열어 시험하려면 또 다른 터미널에서:

```bash
cd ~/idc_ws && source install/setup.bash
python3 tools/mock_mission_state.py --ros-args -r __ns:=/robot5
```

| 입력 | 뜻 |
|---|---|
| `i R17` | R17 응시 시작 — 창 열림 |
| `m` | MARKER_CHECK — 창 유지 |
| `r` | 응시 종료 — **이 순간 판정** |

문이 열린 랙(마커가 가려진 랙) 앞에서 `i R17` → 수 초 → `r` 하면:

```
type: E5
rack_id: R17
basis: marker_missing
```

> **`basis` 두 종류** — `yolo`는 열린 문을 직접 검출한 경우(학습 모델 필요),
> `marker_missing`은 마커가 문에 붙어 있어 문이 열리면 가려지는 성질을 이용한 경우입니다.
> 학습 모델이 없는 동안에는 후자만 사용합니다.

### 3-6. CPU

```bash
top -bn1 | head -15      # 기준 ≤50%
```

---

## 4. 종료

터미널마다 `Ctrl+C`. 원격 확인을 위해 켜 둔 채로 자리를 떠도 됩니다.

---

## 5. 증상별 진단

| 증상 | 원인 | 대처 |
|---|---|---|
| `process has died [exit code 1]`이 2초마다 반복 | venv 미활성화 (PyTorch 못 찾음) | 2-4 재실행. **launch를 띄우는 터미널에서도** activate 필요 |
| objects Hz 0인데 카메라 compressed는 흐름 | compressed→raw 변환의 QoS 불일치 | 코드에서 수정됨. 2-1의 커밋이 최신인지 확인 |
| `rack_id`가 옆 랙 번호 | 화면 중앙 계산(cx) 오류 | 기동 로그의 `cx` 확인. 카메라 폭의 절반이어야 함(704 → 352) |
| `cx`가 폭의 절반이 아님 | `camera_info` 미수신 | `ros2 topic hz /robot5/oakd/rgb/camera_info` → 안 오면 R1 |
| `Package 'idc_perception' not found` | `source install/setup.bash` 누락 | 터미널마다 실행 |
| `perception.launch.py` 없음 | 인식 코드가 없는 리비전 | 2-1 확인 |
| `model_path 파라미터가 비어 있음` | 경로 오타 | `ls ~/idc_ws/models/` |
| `markers=[]`만 나옴 | 마커가 화면 밖·너무 멀리·조명 부족 | 랙 정면 60cm, `image_annotated`로 확인 |
| `nvidia-smi` 사용률 0% | CPU로 실행 중 | `device:=0` 전달 여부, 2-4가 `OK True`였는지 |
| PC3에서 `no new messages` | Discovery 설정 불일치 | 3-2 → R1 |
| `racks=56`이 아님 | `racks.yaml` 문제 | PM에게 |
| CPU 100% 고정 | GPU 미사용 | 위 `nvidia-smi` 항목 |

**yolo_node가 죽어도 마커 인식과 `objects` 발행은 계속됩니다.**
`perception_node`가 `DEGRADED_YOLO`를, 이벤트 엔진이 `DEGRADED`를 로그로 남기고 순찰은 지속됩니다.
`door_state`는 `""`가 되어 문 판정 분모에서 제외되므로, 마커 근거(`marker_missing`) 경로는 살아 있습니다.

---

## 6. 주의

- **로봇 본체(RPi)에는 아무것도 설치·수정하지 않습니다.**
- **공통 파일(`racks.yaml`, launch, `package.xml`)을 고치지 않습니다.** 값이 안 맞으면 PM에게.
- 현장 PC에서 `git push` 하지 않습니다.
- 로봇을 움직일 때 주변 사람·케이블을 확인합니다.

---

## 7. 보고 항목

측정 후 아래를 PM에게 전달합니다.

- 담당 PC, 실행 시각, `git log --oneline -1` 커밋
- venv 확인 결과 (`OK True` / `OK False` / 에러)
- objects Hz · YOLO FPS · GPU 사용률 · CPU 사용률 (Nav2 동시 실행 여부 포함)
- 기동 로그의 `cx` 값
- `image_annotated`에 중앙선·박스가 보이는지
- `rack_id`가 실제 마커 번호와 일치하는지 (확인한 랙 번호 / 실제 마커 / 화면 `rack_id`)
- PC3: 3-2 환경변수 일치 여부, `racks=56`, 두 로봇 objects 수신 여부, mock E5 발생 여부, CPU

---

## 8. 관련 문서

- SDD 5.4 인식 노드 · 5.5 이벤트 엔진 · 7장 노드 다운 처리 · 9장 실행 시나리오
- `src/idc_bringup/config/racks.yaml` — 랙·존·도크 단일 정본(SoT)
- `src/idc_perception/config/perception_params.yaml` — 인식 노드 기본 파라미터
- `src/idc_event/config/event_rules.yaml` — E5 판정 임계값

---

## 9. 1차 실행에서 고친 것

| # | 문제 | 조치 |
|---|---|---|
| 1 | 코드가 있는 리비전이 아닌 `main`을 받아 옛 스텁이 실행됨 | 2-1에 리비전 확인 단계 추가 |
| 2 | PyTorch가 venv 안에 있는데 활성화 안내가 없어 yolo_node가 반복 재기동 | 2-4 신설 |
| 3 | compressed→raw 변환이 QoS 불일치로 조용히 0Hz | launch에 `qos_overrides`(best_effort) 적용 — 담당자 조치 불필요 |
| 4 | 카메라 폭이 640이 아니라 704여서 중앙 랙을 옆 랙으로 오인 가능 | `camera_info`에서 자동 산출 — 담당자 조치 불필요 |
| 5 | GPU 유무를 몰라 `device:=cpu`로 안내 | 기본 `device:=0` |
| 6 | Discovery Server 구성이 문서와 실제가 다름 | 3-2 신설 |
