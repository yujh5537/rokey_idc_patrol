# idc_web

W-owned control/web workspace.

`idc_web` 아래에서 ROS↔MQTT Bridge, FastAPI/PostgreSQL Backend, React Frontend를 함께 관리한다.
소스 코드는 한 디렉터리에서 관리하지만 **실제 실행 환경은 PC3와 PC4로 분리**한다.

- **PC3 (`192.168.107.21`)**: ROS 2 Jazzy + Fast DDS Discovery Server + `idc_bridge`
- **PC4 (`192.168.107.124`)**: Mosquitto + FastAPI + PostgreSQL + React
- **PC4는 ROS 2에 참여하지 않는다.**
- 현재 로봇 네임스페이스: `/robot5`, `/robot11`
- `ROS_DOMAIN_ID=2`

---

## 1. Architecture Boundary

```text
TurtleBot4 / ROS 2 graph
  /robot5
  /robot11
      │
      ▼
PC3 192.168.107.21
  ROS 2 + Fast DDS + idc_bridge
      │
      ├── Battery / MissionState / Pose → MQTT JSON
      └── 후속: Nav status / SecurityEvent / Command / Bridge status
      │
      ▼ MQTT
PC4 192.168.107.124
  Mosquitto
      │
      ▼
  FastAPI MQTT Consumer
      │
      ▼
  PostgreSQL
      │
      ├── REST
      └── 후속 WebSocket
          │
          ▼
        React
```

경계 원칙:

- PC4에 ROS 2, `rclpy`, DDS 의존성을 추가하지 않는다.
- ROS 상태/이벤트/명령 경계는 PC3의 `idc_bridge`가 담당한다.
- Map(`.yaml`, `.pgm`)은 MQTT가 아니라 PC3→PC4 SSH/rsync로 전달한다.
- Snapshot 이미지는 후속 `/server/snapshot` → HTTP `POST /api/v1/evidence` 경로를 사용한다.
- Camera 영상은 후속 PC3 `web_video_server` MJPEG를 React에서 embed한다.

기준 계약:

```text
docs/mqtt_interface_v1.md
```

---

## 2. Repository Structure

```text
src/idc_web/
├── idc_bridge/              # ROS 2 ↔ MQTT Bridge / PC3
│   ├── package.xml
│   ├── setup.py
│   ├── setup.cfg
│   ├── resource/
│   │   └── idc_bridge
│   └── idc_bridge/
│       ├── __init__.py
│       └── mqtt_bridge.py
│
├── backend/                 # FastAPI + PostgreSQL + MQTT / PC4
│   ├── COLCON_IGNORE
│   ├── __init__.py
│   ├── main.py
│   ├── mqtt_consumer.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schema.sql
│   ├── mosquitto.conf
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/                # React + Vite / PC4
    ├── COLCON_IGNORE
    ├── package.json
    ├── package-lock.json
    └── src/
```

`src/idc_web` 자체에는 `COLCON_IGNORE`를 두지 않는다.
`colcon`이 하위 ROS 패키지인 `src/idc_web/idc_bridge`를 찾아야 하기 때문이다.

Web-only 디렉터리는 각각 제외한다.

```text
src/idc_web/backend/COLCON_IGNORE
src/idc_web/frontend/COLCON_IGNORE
```

---

# 3. Current Implementation Status — SRV-02

SRV-02 기준으로 현재 다음 telemetry 경로가 구현 및 E2E 검증되어 있다.

| ROS Source | MQTT Topic | MQTT QoS | Retain | PC4 저장 |
|---|---|---:|---|---|
| `/robotN/battery_state` | `idc/{robot}/battery` | 1 | false | `robots.battery`, `last_seen` |
| `/robotN/mission/state` | `idc/{robot}/mission/state` | 1 | false | `robots.state`, `last_seen` |
| TF `map → base_link` | `idc/{robot}/pose` | 0 | false | `robots.x/y/yaw`, `last_seen` |

Pose는 **2 Hz**로 publish한다.
Battery는 최신 ROS 값을 **1 Hz**로 전달한다.

PC4 FastAPI 현재 REST 범위:

```http
GET /api/v1/health
GET /api/v1/robots
GET /api/v1/robots/{robot_id}
GET /api/v1/events
```

`GET /api/v1/events` 선택 필터:

```text
type
status
robot_id
rack_id
zone_id
limit=1..500 (default 100)
```

SRV-02 실기 검증 문서:

```text
docs/validation/SRV-02_robot_telemetry_e2e_20260908.md
```

API 응답시간 검증 스크립트:

```text
docs/validation/SRV-02_api_runtime_check.sh
```

현재 SRV-02 실측 결과:

```text
robots API         HTTP 200  0.003355s
robot detail API   HTTP 200  0.002503s
events API         HTTP 200  0.003848s
```

모두 SRV-02 기준인 **1.0초 미만**을 충족했다.

> MissionState ingestion은 SRV-02 ROS 2 test publisher로 경로를 검증했다. 실제 `mission_manager` publisher와의 통합은 MIS 통합 시험에서 별도로 검증한다.

---

# 4. PC3 — idc_bridge

## 4-1. 패키지 확인 및 빌드

PC3에서 프로젝트 루트로 이동한다.

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
```

패키지 확인:

```bash
colcon list | grep idc_bridge
```

정상:

```text
idc_bridge    src/idc_web/idc_bridge
```

빌드:

```bash
colcon build \
  --symlink-install \
  --packages-select idc_bridge

source install/setup.bash
```

확인:

```bash
ros2 pkg list | grep '^idc_bridge$'
```

---

## 4-2. PC4 MQTT Broker 연결 확인

```bash
ping -c 3 192.168.107.124
```

Broker 기본값:

```text
Host: 192.168.107.124
Port: 1883
```

---

## 4-3. idc_bridge 실행 — robot5

> Pose를 정상 수신하려면 로봇별 `/tf`, `/tf_static` remap이 필요하다.

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -p map_frame:=map \
  -p base_frame:=base_link \
  -r /tf:=/robot5/tf \
  -r /tf_static:=/robot5/tf_static
```

주요 흐름:

```text
/robot5/battery_state
→ idc/robot5/battery

/robot5/mission/state
→ idc/robot5/mission/state

map → base_link TF
→ idc/robot5/pose
```

---

## 4-4. idc_bridge 실행 — robot11

별도 터미널에서 실행한다.

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot11 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -p map_frame:=map \
  -p base_frame:=base_link \
  -r /tf:=/robot11/tf \
  -r /tf_static:=/robot11/tf_static
```

---

# 5. PC4 — PostgreSQL

PC4에서 실행한다.

```bash
sudo systemctl start postgresql
systemctl is-active postgresql
```

정상:

```text
active
```

부팅 시 자동 시작:

```bash
sudo systemctl enable postgresql
```

---

# 6. PC4 — Mosquitto MQTT Broker

프로젝트 설정 파일:

```text
src/idc_web/backend/mosquitto.conf
```

Broker 실행:

```bash
cd ~/collaboration/rokey_idc_patrol

mosquitto \
  -c src/idc_web/backend/mosquitto.conf \
  -v
```

다른 터미널에서 포트 확인:

```bash
ss -lntp | grep 1883
```

MQTT 전체 토픽 확인:

```bash
mosquitto_sub \
  -h 127.0.0.1 \
  -p 1883 \
  -t 'idc/#' \
  -v
```

예상 토픽:

```text
idc/robot5/battery
idc/robot5/mission/state
idc/robot5/pose
idc/robot11/battery
idc/robot11/mission/state
idc/robot11/pose
```

---

# 7. PC4 — FastAPI Backend

## 7-1. 가상환경 및 의존성

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/backend

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`backend`를 Python package로 import하기 위해 실행은 `src/idc_web`에서 한다.

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web
source backend/.venv/bin/activate
```

---

## 7-2. FastAPI 실행

```bash
uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000
```

FastAPI lifespan에서 `MqttTelemetryConsumer`가 같이 시작되어 MQTT telemetry를 PostgreSQL에 반영한다.

---

## 7-3. Health / REST 확인

Health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Robot list:

```bash
curl http://127.0.0.1:8000/api/v1/robots
```

robot5:

```bash
curl http://127.0.0.1:8000/api/v1/robots/robot5
```

Events:

```bash
curl http://127.0.0.1:8000/api/v1/events
```

필터 예시:

```bash
curl 'http://127.0.0.1:8000/api/v1/events?type=E5&robot_id=robot5&limit=20'
```

---

## 7-4. SRV-02 응답시간 검증

프로젝트 루트에서:

```bash
cd ~/collaboration/rokey_idc_patrol
bash docs/validation/SRV-02_api_runtime_check.sh
```

다른 로봇을 검사하려면:

```bash
ROBOT_ID=robot11 \
bash docs/validation/SRV-02_api_runtime_check.sh
```

기준:

```text
각 API HTTP 2xx
응답시간 < 1.0 s
```

---

# 8. PC4 — React Frontend

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/frontend
npm install
npm run dev -- --host 0.0.0.0
```

예:

```text
http://192.168.107.124:5173
```

SRV-02는 Backend ingestion/REST까지의 작업이며, 실시간 WebSocket UI 연동은 후속 SRV 작업에서 확장한다.

---

# 9. 전체 실행 순서

## PC4 Terminal 1 — PostgreSQL

```bash
sudo systemctl start postgresql
systemctl is-active postgresql
```

## PC4 Terminal 2 — Mosquitto

```bash
cd ~/collaboration/rokey_idc_patrol
mosquitto -c src/idc_web/backend/mosquitto.conf -v
```

## PC4 Terminal 3 — FastAPI

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web
source backend/.venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## PC4 Terminal 4 — MQTT 관측(선택)

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'idc/#' -v
```

## PC4 Terminal 5 — React(필요 시)

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/frontend
npm run dev -- --host 0.0.0.0
```

## PC3 Terminal — robot5 bridge

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -r /tf:=/robot5/tf \
  -r /tf_static:=/robot5/tf_static
```

robot11은 별도 터미널에서 namespace와 TF remap을 `/robot11`로 바꿔 실행한다.

---

# 10. COLCON_IGNORE Policy

```text
src/idc_web/
├── idc_bridge      → colcon 대상
├── backend         → COLCON_IGNORE
└── frontend        → COLCON_IGNORE
```

확인:

```bash
cd ~/collaboration/rokey_idc_patrol
colcon list
```

`idc_bridge`는 나타나야 하고 `backend`, `frontend`는 ROS 패키지로 나타나면 안 된다.

---

# 11. Current Bridge Scope vs Follow-up

현재 구현 완료:

```text
Battery                    ✅
Mission State              ✅
Pose (2 Hz)                ✅
PC4 MQTT → PostgreSQL      ✅
GET /api/v1/robots         ✅
GET /api/v1/robots/{id}    ✅
GET /api/v1/events         ✅
SRV-02 API < 1s 검증       ✅
```

후속 Bridge/SRV 작업:

```text
Nav Status                 ⬜ BRG-01 잔여
SecurityEvent ROS→MQTT     ⬜ 후속 통합
Web→ROS Command            ⬜ BRG-02
Command Result             ⬜ BRG-02
Bridge Status / retained LWT ⬜ BRG-03
Broker outage local queue  ⬜ BRG-03
Evidence / Snapshot        ⬜ SRV-04 + BRG-02
WebSocket realtime push    ⬜ SRV-03/SRV-05 계열
```

따라서 **SRV-02는 완료 기준을 충족하지만 BRG-01 전체가 완료된 것은 아니다.**

---

# 12. Validation References

```text
docs/mqtt_interface_v1.md
docs/validation/SRV-02_robot_telemetry_e2e_20260908.md
docs/validation/SRV-02_api_runtime_check.sh
```

SRV-02 기준 E2E:

```text
ROS 2
→ PC3 idc_bridge
→ MQTT
→ PC4 Mosquitto
→ FastAPI MQTT Consumer
→ PostgreSQL
→ REST
```

이 경로의 Battery / MissionState / Pose가 검증된 상태다.
