# INT-00 — REP-03/#12 ROS→Web integration acceptance

> Decision: **2026-09-11 — INT-00 is accepted against the latest merged REP-03 / PR #12 interface.**
> The retired `Snapshot.srv` / `evidence_id` flow is **not** part of INT-00 acceptance.

## 1. Frozen scope

INT-00 verifies the following Phase-1 path end to end:

```text
MissionState / SecurityEvent / TF
        ↓ ROS 2
PC3 idc_bridge
        ↓ MQTT
PC4 Mosquitto
        ↓
FastAPI mqtt_consumer
        ↓
PostgreSQL
        ↓
REST + WebSocket
        ↓
React map / event UI
```

Source of truth for the ROS contact is the merged repository interface, not stale pre-REP-03 fields in the older Word documents.

### MissionState

`/robotN/mission/state` uses:

- `robot_id`
- `state`
- `zone_id`
- `expected_rack_id`
- `rack_idx`
- `rack_total`
- `battery`
- `note`

Old `waypoint_idx` / `waypoint_total` aliases are not accepted.

### SecurityEvent

Global ROS topic:

```text
/event/events
```

Current REP-03/#12 fields:

- `header`
- `type` (`E5`)
- `robot_id`
- `zone_id`
- `rack_id`
- `position`
- `basis` (`yolo | marker_missing`)
- `open_ratio`
- `frames`
- `marker_checked`

The current message does **not** contain `severity`, `evidence_ids`, `detail_json`, or E7. The bridge/backend/UI must not fabricate them.

## 2. MAP-02 coordinate contract used by Web

The coordinate SoT is:

```text
src/idc_bringup/config/racks.yaml
```

Current board contract:

```text
width  = 3.5 m
height = 5.6 m
map origin = [-0.5, -0.5, 0]
resolution = 0.05 m/px
```

Fallback/AMCL initial dock poses:

```text
robot11 = (0.27, 4.920, 3.1416)
robot5  = (0.27, 0.330, 3.1416)
```

Robot live pose and rack coordinates are both rendered through the same ROS `map`-frame transform when a real PGM/YAML map is loaded. Display-only offsets are not permitted in the real-map path.

## 3. Implemented integration state

### PC3 bridge

- `/robotN/mission/state` → `idc/{robot}/mission/state`, QoS 1
- TF `map → {robot}/base_link` → `idc/{robot}/pose`, QoS 0, 2 Hz
- `/event/events` → `idc/events/security`, QoS 1
- one bridge process per robot namespace
- global SecurityEvent is filtered by configured `robot_id`
- event payload is persisted to a per-robot SQLite outbox before MQTT publish
- outbox row is removed only after PUBACK
- reconnect/restart replay preserves original `stamp` and `received_at`
- delivery contract is **at least once**, not exactly once

### PC4 backend

- subscribes to battery / mission state / pose / security event
- seeds `Z1..Z4` and `R01..R56` static identity/coordinates from MAP-02 before MQTT consumption
- rejects unknown zone/rack references rather than silently inventing them
- persists SecurityEvent E5 into `events`
- stores REP-03 diagnostic fields inside `detail_json` only as backend persistence metadata
- keeps DB `severity` and `status` NULL because the current ROS event does not provide them
- deduplicates at-least-once event replay using robot/type/rack/source timestamp
- `/api/v1/events` exposes persisted events
- `/api/v1/ws` sends `robot_pose` and new `event_new` messages

### React

- initial robots: `/api/v1/robots`
- initial events: `/api/v1/events`
- live robot positions: WebSocket `robot_pose`
- live security events: WebSocket `event_new`
- event marker is attached to the matching MAP-02 `rack_id`
- no fake severity is added when the backend event has none
- demo E5/E7 values exist only after explicitly selecting the demo controls

## 4. Automated verification already available

Bridge contract test:

```bash
python3 -m unittest discover -s src/idc_web/idc_bridge/test -v
```

Expected baseline: **13 offline tests pass**.

Coverage includes:

- merged REP-03 MissionState field names
- both E5 bases (`yolo`, `marker_missing`)
- both robot bridge instances
- PUBACK ordering
- broker disconnect while publishing
- SQLite queue persistence / restart / FIFO replay
- preserved source/receive timestamps
- NaN/Inf JSON handling
- battery and pose regression

This test is offline. It does not replace live DDS/Mosquitto/PostgreSQL/browser acceptance.

## 5. Live acceptance procedure

### 5.1 PC4 — start broker/backend/frontend

```bash
cd ~/collaboration/rokey_idc_patrol
git switch euiseok/20260910-srv03-int00-integration
git pull

sudo systemctl start postgresql

# Use only one Mosquitto instance on :1883.
sudo systemctl stop mosquitto 2>/dev/null || true
pkill -f 'mosquitto -c .*src/idc_web/backend/mosquitto.conf' 2>/dev/null || true
mosquitto -c src/idc_web/backend/mosquitto.conf -v
```

Keep Mosquitto open, then use a new PC4 terminal:

```bash
cd ~/collaboration/rokey_idc_patrol
python3 -m venv src/idc_web/backend/.venv
source src/idc_web/backend/.venv/bin/activate
pip install -r src/idc_web/backend/requirements.txt

cd src/idc_web
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Backend startup must complete without MAP-02 seed errors.

In another PC4 terminal:

```bash
curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/v1/robots | python3 -m json.tool
curl -s 'http://127.0.0.1:8000/api/v1/events?limit=20' | python3 -m json.tool
```

Then frontend:

```bash
cd ~/collaboration/rokey_idc_patrol/src/idc_web/frontend
npm install
npm run dev
```

### 5.2 PC4 — observe MQTT before producing events

```bash
mosquitto_sub -h 192.168.107.124 -p 1883 \
  -t 'idc/+/battery' \
  -t 'idc/+/pose' \
  -t 'idc/+/mission/state' \
  -t 'idc/events/security' -v
```

### 5.3 PC3 — build and verify merged interfaces

```bash
cd ~/collaboration/rokey_idc_patrol
git switch euiseok/20260910-srv03-int00-integration
git pull

source /opt/ros/jazzy/setup.bash
source ~/.bashrc

colcon build --symlink-install --packages-select idc_msgs idc_bridge
source install/setup.bash

ros2 interface show idc_msgs/msg/MissionState
ros2 interface show idc_msgs/msg/SecurityEvent
```

`MissionState` must show `rack_idx/rack_total`; `SecurityEvent` must show `basis/open_ratio/frames/marker_checked` and must not show the retired evidence/severity fields.

### 5.4 PC3 — run one bridge per robot

robot5 terminal:

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
source ~/.bashrc
source install/setup.bash

ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -r /tf:=/robot5/tf \
  -r /tf_static:=/robot5/tf_static
```

robot11 terminal:

```bash
cd ~/collaboration/rokey_idc_patrol
source /opt/ros/jazzy/setup.bash
source ~/.bashrc
source install/setup.bash

ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot11 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -r /tf:=/robot11/tf \
  -r /tf_static:=/robot11/tf_static
```

Do not run two bridge instances for the same robot.

### 5.5 Observe the ROS source

```bash
ros2 topic echo /event/events
```

For robot state/pose regression checks:

```bash
ros2 topic echo /robot5/mission/state --once
ros2 topic echo /robot11/mission/state --once
ros2 topic echo /robot5/battery_state --once
ros2 topic echo /robot11/battery_state --once
```

## 6. PASS criteria

INT-00 is PASS only when all of the following are captured from the deployment PCs:

1. `MissionState` reaches MQTT with `rack_idx`, `rack_total`, `zone_id`, and `expected_rack_id` without legacy waypoint-field errors.
2. A real `/event/events` E5 from robot5 reaches `idc/events/security` once on the normal path and contains the exact REP-03/#12 diagnostic fields.
3. Repeat for robot11; each bridge forwards only the event whose `robot_id` matches its configured namespace.
4. The same E5 is persisted in PostgreSQL and returned by `/api/v1/events` with the correct `robot_id`, `zone_id`, `rack_id`, x/y and diagnostic detail.
5. React receives `event_new` and marks the exact rack on the MAP-02 map. No fabricated severity/evidence is displayed.
6. Live robot5 and robot11 pose markers are rendered from MQTT/DB/WebSocket coordinates using the same map-frame conversion as rack markers.
7. Battery and pose telemetry still work after the event-path changes.
8. During an intentional broker interruption, an E5 remains in the PC3 outbox and is replayed after reconnect with unchanged source/receive timestamps; PC4 stores only one logical event after duplicate replay.
9. Browser refresh does not duplicate already-loaded events.

## 7. Explicitly out of scope for this INT-00 baseline

The following are not required and must not be reintroduced merely to satisfy an older schedule row:

- retired `Snapshot.srv`
- `evidence_id` callback
- SecurityEvent `severity`
- SecurityEvent `evidence_ids`
- SecurityEvent `detail_json`
- E7 event production
- direct annotated-image ingestion by the Web backend

If a later PM-approved interface adds these back, treat that as a new controlled interface revision rather than silently extending REP-03/#12.
