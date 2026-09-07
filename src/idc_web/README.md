# idc_web

W-owned control/web workspace.

`idc_web` 아래에 ROS↔MQTT Bridge, FastAPI/PostgreSQL Backend, React Frontend를 함께 관리한다.

소스 코드는 하나의 디렉터리에서 관리하지만 실제 실행 환경은 ADR-001 기준으로 분리한다.

- **PC3**: ROS 2 + `idc_bridge`
- **PC4**: Mosquitto + FastAPI + PostgreSQL + React
- **PC4는 ROS 2에 참여하지 않는다.**

---

## Structure

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

`src/idc_web/COLCON_IGNORE`는 사용하지 않는다.

이유는 `colcon`이 하위의 ROS 2 패키지인 `idc_bridge`를 찾아야 하기 때문이다.

대신 ROS 2 패키지가 아닌 다음 디렉터리에 각각 `COLCON_IGNORE`를 둔다.

```text
src/idc_web/backend/COLCON_IGNORE
src/idc_web/frontend/COLCON_IGNORE
```

따라서 `colcon`은 다음 패키지만 ROS 2 패키지로 인식한다.

```text
src/idc_web/idc_bridge
```

소스 코드 위치와 실제 실행 PC는 별개다.

`idc_bridge`는 `idc_web` 아래에서 함께 관리하지만 **PC3에서 실행**하고,
FastAPI/PostgreSQL/Mosquitto/React는 **PC4에서 실행**한다.

---

# 1. ROS ↔ MQTT Bridge

## 실행 위치

**PC3 — Main / Control ROS PC**

```text
ROS 2
  ↓
idc_bridge
  ↓
MQTT
  ↓
PC4 Mosquitto
```

`idc_bridge`는 ROS 2 그래프에 참여하면서 로봇 데이터를 MQTT 메시지로 변환한다.

현재 이관된 `mqtt_bridge.py`는 기존 `idc_server/mqtt_bridge.py`의 기능을 보존한다.

현재 구현 범위:

```text
/robotN/battery_state
        ↓
idc_bridge/mqtt_bridge.py
        ↓
idc/{robot}/battery
```

BRG-01의 pose/state/event/command 확장은 후속 Bridge 통합 작업에서 진행한다.

---

## 1-1. idc_bridge 패키지 확인

워크스페이스 루트에서 실행한다.

```bash
cd ~/collaboration/rokey_idc_patrol
```

```bash
colcon list | grep idc_bridge
```

정상이라면 다음과 같이 `idc_bridge`가 출력되어야 한다.

```text
idc_bridge    src/idc_web/idc_bridge
```

---

## 1-2. idc_bridge 빌드

```bash
cd ~/collaboration/rokey_idc_patrol

source /opt/ros/jazzy/setup.bash

colcon build \
  --symlink-install \
  --packages-select idc_bridge
```

빌드 후:

```bash
source install/setup.bash
```

패키지 확인:

```bash
ros2 pkg list | grep idc_bridge
```

정상:

```text
idc_bridge
```

---

## 1-3. MQTT Broker 연결 확인

PC4의 Mosquitto Broker IP:

```text
192.168.107.124
```

기본 MQTT Port:

```text
1883
```

PC3에서 네트워크 연결 확인:

```bash
ping -c 3 192.168.107.124
```

---

## 1-4. mqtt_bridge 실행

### robot5

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883
```

현재 Bridge는 다음 흐름으로 동작한다.

```text
/robot5/battery_state
        ↓
idc_bridge
        ↓
idc/robot5/battery
        ↓
Mosquitto
```

### robot11

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot11 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883
```

---

# 2. PC4 Web/Data Plane

## 실행 위치

**PC4 — Web / DB Server**

```text
192.168.107.124
```

PC4의 역할:

```text
Mosquitto
   ↓
FastAPI
   ↓
PostgreSQL
   ↓
WebSocket
   ↓
React
```

PC4는 ADR-001 기준으로 **ROS 2를 사용하지 않는다.**

즉 PC4에서는 다음을 하지 않는다.

```text
rclpy 사용
ROS Topic 직접 Subscribe
ROS Service/Action 직접 호출
DDS 참여
```

ROS 2와 Web/Data Plane 사이의 연결은 PC3의 `idc_bridge`가 담당한다.

---

# 3. PostgreSQL

## 3-1. PostgreSQL 서비스 시작

PC4에서 실행한다.

```bash
sudo systemctl start postgresql
```

상태 확인:

```bash
sudo systemctl status postgresql
```

간단히 확인하려면:

```bash
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

# 4. Mosquitto MQTT Broker

## 4-1. Mosquitto 설정 파일

프로젝트 설정 파일:

```text
src/idc_web/backend/mosquitto.conf
```

PC4에서 프로젝트 루트로 이동한다.

```bash
cd ~/collaboration/rokey_idc_patrol
```

Mosquitto 실행:

```bash
mosquitto \
  -c src/idc_web/backend/mosquitto.conf \
  -v
```

이 터미널은 Broker 실행용이므로 종료하지 않는다.

기본 포트:

```text
1883
```

---

## 4-2. MQTT Broker 포트 확인

다른 터미널에서:

```bash
ss -lntp | grep 1883
```

또는:

```bash
sudo lsof -i :1883
```

---

## 4-3. MQTT 테스트

구독 터미널:

```bash
mosquitto_sub \
  -h 127.0.0.1 \
  -p 1883 \
  -t 'idc/#' \
  -v
```

PC3에서 `idc_bridge`가 실행되고 로봇 배터리 메시지를 수신하고 있다면 다음과 같은 MQTT Topic이 확인되어야 한다.

```text
idc/robot5/battery
```

또는:

```text
idc/robot11/battery
```

---

# 5. FastAPI Backend

## 5-1. Backend 가상환경 생성

PC4에서:

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/backend
```

가상환경 생성:

```bash
python3 -m venv .venv
```

활성화:

```bash
source .venv/bin/activate
```

의존성 설치:

```bash
pip install -r requirements.txt
```

환경 설정 파일 생성:

```bash
cp .env.example .env
```

---

## 5-2. FastAPI 실행

`backend`를 Python package로 import할 수 있도록 `src/idc_web`에서 실행한다.

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web
```

가상환경 활성화:

```bash
source backend/.venv/bin/activate
```

FastAPI 실행:

```bash
uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000
```

---

## 5-3. Health Check

PC4에서:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

또는 다른 PC에서:

```bash
curl http://192.168.107.124:8000/api/v1/health
```

`/api/v1/health`는 Backend, Database, MQTT Broker 연결 상태 확인에 사용한다.

---

# 6. React Frontend

## 6-1. Frontend 설치

PC4에서:

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/frontend
```

의존성 설치:

```bash
npm install
```

---

## 6-2. React 개발 서버 실행

```bash
npm run dev -- --host 0.0.0.0
```

실행 후 터미널에 표시되는 Vite 주소로 접속한다.

예:

```text
http://192.168.107.124:5173
```

---

# 7. 전체 실행 순서

## PC4

### Terminal 1 — PostgreSQL

```bash
sudo systemctl start postgresql

systemctl is-active postgresql
```

---

### Terminal 2 — Mosquitto

```bash
cd ~/collaboration/rokey_idc_patrol

mosquitto \
  -c src/idc_web/backend/mosquitto.conf \
  -v
```

---

### Terminal 3 — FastAPI

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web

source backend/.venv/bin/activate

uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000
```

---

### Terminal 4 — React

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/frontend

npm run dev -- --host 0.0.0.0
```

---

## PC3

### Terminal — idc_bridge

워크스페이스 환경 적용:

```bash
cd ~/collaboration/rokey_idc_patrol

source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

robot5:

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883
```

robot11을 사용할 경우 별도 터미널:

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot11 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883
```

---

# 8. 전체 데이터 흐름

현재 Web/Data Plane 구조:

```text
TurtleBot4
   │
   │ ROS 2
   ▼
PC3
┌────────────────────────────┐
│ ROS 2                      │
│                            │
│ /robot5/...                │
│ /robot11/...               │
│                            │
│ idc_bridge                 │
└──────────────┬─────────────┘
               │
               │ MQTT
               ▼
PC4
┌────────────────────────────┐
│ Mosquitto :1883            │
│       │                    │
│       ▼                    │
│ FastAPI :8000              │
│       │                    │
│       ├── PostgreSQL       │
│       │                    │
│       └── WebSocket        │
│               │            │
│               ▼            │
│           React            │
└────────────────────────────┘
```

---

# 9. COLCON_IGNORE 정책

`src/idc_web` 자체에는 `COLCON_IGNORE`를 두지 않는다.

```text
src/idc_web/
```

이유:

```text
colcon
  ↓
src/idc_web
  ↓
src/idc_web/idc_bridge/package.xml 발견
  ↓
idc_bridge ROS 패키지 빌드
```

Web-only 디렉터리는 각각 무시한다.

```text
src/idc_web/backend/COLCON_IGNORE
src/idc_web/frontend/COLCON_IGNORE
```

결과적으로:

```text
idc_bridge  → colcon build 대상
backend     → colcon 제외
frontend    → colcon 제외
```

검증:

```bash
cd ~/collaboration/rokey_idc_patrol

colcon list
```

`idc_bridge`는 나타나야 하고 `backend`, `frontend`는 ROS 패키지로 나타나면 안 된다.

---

# 10. Architecture Boundary

소스 관리:

```text
src/idc_web/
├── idc_bridge
├── backend
└── frontend
```

실행 환경:

```text
PC3
└── idc_bridge
     └── ROS 2 ↔ MQTT

PC4
├── Mosquitto
├── FastAPI
├── PostgreSQL
└── React
```

즉 `idc_bridge`가 `idc_web` 디렉터리 안에 존재하더라도 PC4에서 ROS 2를 실행한다는 의미가 아니다.

Repository grouping과 Deployment boundary는 서로 독립적이다.

---

# 11. Current Bridge Scope

현재 `mqtt_bridge.py`는 기존 `idc_server`에서 사용하던 Battery Bridge 기능을 `idc_bridge` ROS 패키지로 이관한 상태다.

현재:

```text
/robotN/battery_state
        ↓
idc_bridge
        ↓
idc/{robot}/battery
```

후속 BRG-01에서는 MQTT Interface v1 계약에 맞춰 다음 항목을 확장한다.

```text
Pose
Mission State
Robot State
Navigation Status
Security Event
Command
Command Result
Bridge Status
```

최종 목표 데이터 경계:

```text
ROS 2
  ↕
idc_bridge
  ↕
MQTT
  ↕
FastAPI
  ↕
PostgreSQL / WebSocket
  ↕
React
```