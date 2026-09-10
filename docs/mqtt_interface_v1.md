# MQTT Interface v1 — IDC Patrol Control/Web Boundary

> Status: **FROZEN v1.0 baseline; INT-00 mapping amendment for merged REP-03 (#9) / Vision (#12)**
> Owner: W (Control Server / Web UI / ROS↔Web boundary)  
> Date: 2026-09-06  
> Related task: SRV-00  
> ROS interface baseline: REP-02 PR #2; MissionState/SecurityEvent below follow merged REP-03 #9 and #12. Other historical sections are not a claim of v2 implementation.

## 1. Architecture boundary

```text
TurtleBot4 / ROS 2 graph
  /robot5
  /robot11
      │
      ▼
PC3 192.168.107.21
  Fast DDS Discovery Server + ROS 2 + idc_bridge
      │
      ├── ROS state/event → MQTT JSON
      ├── MQTT command → ROS service/action
      └── /server/snapshot → HTTP POST /api/v1/evidence
      │
      ▼
PC4 192.168.107.124
  Mosquitto → FastAPI → PostgreSQL → WebSocket/REST → React
```

Boundary rules:

- PC4 does **not** install or join ROS 2.
- Maps (`map.yaml`, `map.pgm`) are transferred PC3→PC4 by SSH/rsync, not MQTT.
- Snapshot image bytes are sent by HTTP `POST /api/v1/evidence`, not MQTT.
- Camera streams are served from PC3 by `web_video_server` as MJPEG and embedded by React; video frames are not MQTT payloads.
- Browser realtime updates use WebSocket, not polling.

## 2. Naming and common JSON rules

MQTT topic prefix:

```text
idc/{robot}/...
```

`{robot}` is the namespace without the leading slash. Current deployment values:

```text
robot5
robot11
```

Do not hardcode these values in source; load them from launch/config parameters.

Common JSON rules:

- Encoding: UTF-8 JSON.
- `schema_version`: `"1.0"`.
- `robot_id`: namespace string without `/`.
- ROS messages with a Header preserve `header.stamp` as `{ "sec": int, "nanosec": int }`.
- Every bridge-produced payload adds `received_at` in UTC ISO-8601.
- NaN/Inf must never be emitted as JSON numbers; emit `null` instead.
- Commands and command results require `request_id` (UUID string) for correlation and duplicate suppression.
- Dynamic telemetry, commands, events, and results are **not retained**.
- Only bridge availability/LWT is retained.

## 3. MQTT topic contract

| Direction | MQTT topic | ROS source/target | MQTT QoS | Retain | Rate / trigger |
|---|---|---|---:|---|---|
| ROS→Web | `idc/{robot}/battery` | `/robotN/battery_state` (`sensor_msgs/BatteryState`) | 1 | false | ≥1 Hz |
| ROS→Web | `idc/{robot}/mission/state` | `/robotN/mission/state` (`idc_msgs/MissionState`) | 1 | false | 2 Hz |
| ROS→Web | `idc/{robot}/pose` | TF `map → {robot}/base_link` | 0 | false | 2 Hz |
| ROS→Web | `idc/{robot}/nav/status` | `/robotN/navigate_to_pose/_action/status` (`action_msgs/GoalStatusArray`) | 1 | false | on status change |
| ROS→Web | `idc/{robot}/perception/objects` | `/robotN/perception/objects` (`idc_msgs/ObjectArray`) | 0 | false | up to 10 Hz; default Web forwarding OFF unless needed |
| ROS→Web | `idc/events/security` | `/event/events` (`idc_msgs/SecurityEvent`) | 1 | false | event |
| Web→ROS | `idc/{robot}/cmd/nav_goal` | Nav2 `NavigateToPose` | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/dock` | Create3 dock action | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/undock` | Create3 undock action | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/stop` | mission/nav safe stop path | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/mission` | mission manager start/stop/return | 1 | false | command |
| ROS→Web | `idc/{robot}/cmd/result` | bridge command result | 1 | false | result |
| Bridge | `idc/{robot}/bridge/status` | bridge availability / LWT | 1 | **true** | connect/disconnect |

### 3.1 `nav/status` exact contract

ROS source:

```text
/robotN/navigate_to_pose/_action/status
```

ROS type:

```text
action_msgs/msg/GoalStatusArray
```

The bridge selects the newest `NavigateToPose` goal by `GoalInfo.stamp`, serializes its ROS UUID as a canonical UUID string, and publishes only when the selected goal status changes. If `status_list` is empty, the bridge does not synthesize an `IDLE` status; mission/UI idle state comes from `MissionState`.

Native ROS 2 GoalStatus mapping is frozen as:

| `status_code` | `status` |
|---:|---|
| 0 | `UNKNOWN` |
| 1 | `ACCEPTED` |
| 2 | `EXECUTING` |
| 3 | `CANCELING` |
| 4 | `SUCCEEDED` |
| 5 | `CANCELED` |
| 6 | `ABORTED` |

Minimum MQTT JSON payload:

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "goal_id": "550e8400-e29b-41d4-a716-446655440000",
  "status_code": 2,
  "status": "EXECUTING",
  "stamp": {"sec": 0, "nanosec": 0},
  "received_at": "2026-09-07T01:00:00.000Z"
}
```

`stamp` is the selected goal's `GoalInfo.stamp`. `received_at` is the PC3 bridge receive time.

### 3.2 Retained policy

`retain=true` is allowed **only** for `idc/{robot}/bridge/status`.

Reason: retaining battery, pose, mission state, event, or command data can resurrect stale state after broker/client reconnect. The UI must derive freshness from timestamps and bridge status instead.

## 4. ROS ↔ MQTT JSON mapping

### 4.1 BatteryState → `idc/{robot}/battery`

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "battery_percent": 74.2,
  "percentage": 0.742,
  "voltage": 24.311,
  "temperature": 31.2,
  "present": true,
  "stamp": {"sec": 0, "nanosec": 0},
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

Mapping:

| ROS `BatteryState` | MQTT JSON | FastAPI / DB | React |
|---|---|---|---|
| `header.stamp` | `stamp` | `robots.last_seen` uses receive time; source stamp preserved separately if needed | freshness indicator |
| `percentage` (0..1) | `percentage`, derived `battery_percent` | `robots.battery` stores 0..1 | card displays `%` |
| `voltage` | `voltage` | telemetry/debug optional | optional |
| `temperature` | `temperature` | telemetry/debug optional | optional |
| `present` | `present` | telemetry/debug optional | optional |

### 4.2 MissionState → `idc/{robot}/mission/state`

Merged REP-03 `MissionState.msg` fields are preserved. This replaces the old
`waypoint_idx` / `waypoint_total` mapping; both ROS field access and JSON keys
use `rack_idx` / `rack_total` (no legacy aliases).

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "state": "INSPECT",
  "zone_id": "Z1",
  "expected_rack_id": "R17",
  "rack_idx": 3,
  "rack_total": 28,
  "battery": 0.71,
  "note": "",
  "received_at": "2026-09-10T12:00:00.000Z"
}
```

States: `INIT | UNDOCK | NAVIGATE | FACE | INSPECT | MARKER_CHECK | RESUME |
RETURN | DOCK | DONE | ERROR`. Preserve source values, including empty zone/rack
strings. MissionState has no Header; `received_at` is the bridge receive time.
Topic, QoS 1, retain false, and transport `schema_version: "1.0"` stay unchanged.
Consumers must deploy with this mapping amendment; the schema version alone
does not distinguish the old waypoint mapping from this rack mapping.

### 4.3 TF pose → `idc/{robot}/pose`

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "frame_id": "map",
  "child_frame_id": "robot5/base_link",
  "x": 1.23,
  "y": 2.34,
  "yaw": 0.52,
  "stamp": {"sec": 0, "nanosec": 0},
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

- Publish at 2 Hz.
- MQTT QoS 0: pose is latest-value telemetry; delayed old pose is worse than a dropped sample.
- React/WebSocket must discard out-of-order/stale samples.

### 4.4 ObjectArray → `idc/{robot}/perception/objects`

REP-02 hierarchy is preserved.

For the frozen SRV-00 v1 Web/event path, `class_name` values consumed over this mapping are exactly:

```text
rack_door_open
rack_door_closed
led_green
led_red
led_off
```

- `rack_door_open`, `rack_door_closed`: YOLO output.
- `led_green`, `led_red`, `led_off`: A1 HSV LED classification result.
- Therefore this five-value Web/event contract is **not** a 1:1 copy of `data.yaml`.

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "stamp": {"sec": 0, "nanosec": 0},
  "objects": [
    {
      "class_name": "rack_door_open",
      "track_id": 12,
      "confidence": 0.93,
      "map_pose": {
        "frame_id": "map",
        "position": {"x": 1.0, "y": 2.0, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
      },
      "low_confidence": false,
      "zone_id": "Z1",
      "rack_id": "R01",
      "identity": ""
    }
  ],
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

This stream can be high-rate; default PC4 forwarding is OFF unless UI/debug requires it. Event detection remains on the ROS side.

### 4.5 SecurityEvent → `idc/events/security`

Merged REP-03 `SecurityEvent.msg` / #12 is the ROS source for this mapping.
The bridge forwards the event result; it does not run the E5 judgement again.

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "type": "E5",
  "zone_id": "Z1",
  "rack_id": "R17",
  "position": {"x": 2.975, "y": 4.1575, "z": 0.0},
  "basis": "yolo",
  "open_ratio": 0.8,
  "frames": 15,
  "marker_checked": false,
  "stamp": {"sec": 123, "nanosec": 456},
  "received_at": "2026-09-10T12:00:00.000Z"
}
```

- `basis`: `yolo | marker_missing`; `open_ratio`: float (null for NaN/Inf);
  `frames`: integer door observation frame count; `marker_checked`: boolean.
- `severity`, `evidence_ids`, `detail_json`, and E7 are not fields/results of the
  current ROS event interface. Do not fabricate these in the bridge JSON.
- `/event/events` is global. Run one bridge per robot namespace; each forwards
  only events whose `robot_id` exactly matches its configured robot. Both use
  `idc/events/security`, MQTT QoS 1, retain false.
- Events are committed to a per-robot SQLite outbox before MQTT publish.
  Default: `~/.ros/idc_bridge/{robot}-events.sqlite3`; override with ROS parameter
  `event_queue_path`. Use separate paths for different robot instances.
- Broker unavailable at startup: bridge still starts, receives ROS events and
  queues them. Retry after reconnect preserves `stamp` and `received_at`.
- Queue rows are removed only after broker PUBACK, not merely `publish()` success.
  Delivery is at least once: a crash after PUBACK but before queue deletion can
  replay an event. Downstream consumers must deduplicate source events.
- PUBACK confirms broker receipt, **not** FastAPI/DB commit. This amendment does
  not implement a backend application ACK or claim DB-outage recovery.
- PC4 security-event ingestion and browser `event_new` are separate from this
  bridge patch. See `docs/validation/INT-00_bridge_interface.md` for acceptance.

### 4.6 Command → ROS action/service

Command payload base:

```json
{
  "schema_version": "1.0",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "robot_id": "robot5",
  "issued_at": "2026-09-06T07:00:00.000Z",
  "params": {}
}
```

`nav_goal` params:

```json
{
  "frame_id": "map",
  "x": 1.5,
  "y": 2.0,
  "yaw": 0.0
}
```

`mission` params:

```json
{
  "action": "start"
}
```

Allowed mission actions for v1: `start | stop | return`.

Command result topic: `idc/{robot}/cmd/result`

```json
{
  "schema_version": "1.0",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "robot_id": "robot5",
  "command": "nav_goal",
  "accepted": true,
  "success": true,
  "status": "SUCCEEDED",
  "message": "",
  "completed_at": "2026-09-06T07:00:03.100Z"
}
```

Rules:

- Bridge caches recently processed `request_id` values to suppress duplicate execution caused by MQTT QoS 1 redelivery.
- `accepted` means ROS action/service accepted the request; `success` means final execution succeeded.
- Unknown commands/invalid payloads return a failed result; they must not be silently ignored.

## 5. Bridge availability / LWT

Topic:

```text
idc/{robot}/bridge/status
```

On successful MQTT connection, bridge publishes retained:

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "online": true,
  "connected_at": "2026-09-06T07:00:00.000Z"
}
```

MQTT Last Will is configured before connect with retained payload:

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "online": false,
  "reason": "lwt"
}
```

UI rule: if bridge is offline, previously cached robot state must be displayed as stale/offline, never as a current live state.

## 6. `/server/snapshot` path — ROS service is preserved

REP-02 `Snapshot.srv` remains the external ROS contract for R3/MIS-05.

```text
R3 mission_manager
  → ROS /server/snapshot
  → PC3 idc_bridge snapshot_service
  → HTTP POST /api/v1/evidence
  → PC4 FastAPI stores file + SHA-256 + DB row
  → HTTP response
  → ROS Snapshot response(success, evidence_id, sha256, message)
```

No snapshot image bytes are sent over MQTT.

FastAPI evidence request: `multipart/form-data`

- `image`: JPEG file body
- `metadata`: JSON string containing `robot_id`, `event_type`, `rack_id`, `zone_id`, `position`, `detail_json`, and source stamp

Response:

```json
{
  "success": true,
  "evidence_id": 101,
  "sha256": "...",
  "message": ""
}
```

## 7. REST `/api/v1` contract

Minimum v1 resources required by SRD/SRV work are listed below. Reserved endpoints remain in the interface namespace so future expansion does not require reopening the frozen naming contract.

| Method | Path | Purpose / v1 scope |
|---|---|---|
| GET | `/api/v1/health` | backend/database/broker health |
| GET | `/api/v1/robots` | robot cards/state |
| GET | `/api/v1/robots/{robot_id}` | one robot state |
| POST | `/api/v1/robots/{robot_id}/commands` | publish MQTT command, return `request_id` |
| GET | `/api/v1/events` | event list/filter |
| GET | `/api/v1/events/{event_id}` | event detail |
| POST | `/api/v1/events/{event_id}/ack` | operator ACK + audit log |
| POST | `/api/v1/evidence` | snapshot image + metadata → evidence_id |
| GET | `/api/v1/maps/current` | **v1 구현 범위 외 — 스키마/경로만 예약** |
| GET | `/api/v1/patrol-runs` | patrol history |
| GET | `/api/v1/waypoints` | patrol route read; source of truth is R2 NAV-03 `patrol_routes.yaml` |
| PUT | `/api/v1/waypoints` | **v1 구현 범위 외 — 쓰기 권한/경로만 예약** |
| GET/PUT | `/api/v1/zones` | zone/policy read/update |
| GET | `/api/v1/racks` | rack metadata |
| GET/POST/DELETE | `/api/v1/persons` | **v1 구현 범위 외 — 스키마/경로만 예약** |
| GET/POST | `/api/v1/auth-events` | **v1 구현 범위 외 — 스키마/경로만 예약** |
| GET | `/api/v1/audit-log` | audit chain query/verification |

## 8. WebSocket contract

WebSocket endpoint:

```text
/api/v1/ws
```

Event names kept close to the SDD data-flow naming:

```text
robot_pose       # 2 Hz
robot_state
robot_battery
bridge_status
event_new
event_update
people_count
command_result
```

Envelope:

```json
{
  "event": "robot_pose",
  "data": {},
  "server_ts": "2026-09-06T07:00:00.000Z"
}
```

Target: event generation → browser display ≤0.5 s for the v3 G3 path.

## 9. PostgreSQL logical schema (10 tables)

The logical table set is fixed by SRD SR-F28:

```text
robots
patrol_runs
waypoints
zones
racks
persons
auth_events
events
evidence
audit_log
```

Use SQLAlchemy so PostgreSQL and the approved fallback SQLite can share models by changing only `DATABASE_URL`.

### 9.1 Frozen rack and zone identifier contract

- `rack_id` is a string in the range/pattern `R01` ... `R56`.
- `racks.id` stores that string and is the canonical rack identifier used by ROS→MQTT→FastAPI→DB→React.
- `aruco_id` is derived as `int(rack_id[1:])`; for example `R01 → 1`, `R56 → 56`.
- `baseline_led` values are exactly `green | red` for the v1 baseline.
- `zone_id` is a string in the range/pattern `Z1` ... `Z4`.
- `zones.id` stores that string and is the canonical zone identifier used by ROS→MQTT→FastAPI→DB→React.

Baseline columns are inherited from SDD 4.2.4 with the frozen rack/zone identifier clarification above:

- `robots(id, name, last_seen, battery, state, x, y, yaw)`
- `patrol_runs(id, started_at, ended_at, map_id, coverage, status)`
- `waypoints(id, run_id, robot_id, seq, x, y, yaw, rack_id, visited_at, result)`
- `zones(id STRING PK [Z1..Z4], name, polygon_json, allowed_from, allowed_to, min_persons, max_dwell_sec, allowed_person_ids)`
- `racks(id STRING PK [R01..R56], aruco_id INTEGER derived from id, x, y, yaw, zone_id, baseline_door, baseline_led [green|red])`
- `persons(id, name, org, consent_id, embedding, registered_at, revoked_at)`
- `auth_events(id, person_id, door_id, ts)`
- `events(id, run_id, type, severity, zone_id, rack_id, robot_id, x, y, first_ts, last_ts, status, acked_by, acked_at, detail_json)`
- `evidence(id, event_id, robot_id, ts, path_blurred, path_encrypted, sha256, x, y, yaw)`
- `audit_log(id, ts, actor, action, target, detail, prev_hash, hash)`

Physical PostgreSQL types/constraints/indexes are implemented in SRV-01/SRV-02; field semantics above are the SRV-00 contract.

## 10. Five-layer consistency checklist

Any field change must update this chain first and be reported to PM:

```text
ROS msg
  ↕
MQTT JSON
  ↕
FastAPI/Pydantic model
  ↕
SQLAlchemy/PostgreSQL column
  ↕
React TypeScript type
```

REP-02 ROS fields are owned/frozen by P after review. W may add transport metadata such as `schema_version`, `received_at`, and `request_id`, but must not rename/remove REP-02 fields in the mapping.

## 11. REP-02 review notes at Freeze

The schemas are usable from the W boundary perspective. REP-02 message/service fields are not changed by SRV-00.

1. `robot_id` is interpreted generically as the ROS namespace without the leading slash; the current deployment values are `robot5` and `robot11`.
2. In v3, PC3 `idc_bridge` owns the ROS boundary and PC4 is ROS-free. `/server/snapshot` is preserved as the REP-02 ROS service and forwarded from PC3 to PC4 over HTTP.
3. `MissionState.msg` intentionally follows SDD 4.2.3 and has no Header; the bridge adds `received_at` rather than changing REP-02.

## 12. Freeze checklist

SRV-00 is complete only after all are checked. Review completion was recorded on PR #3; PR #4 is the final freeze/acceptance PR.

- [x] MQTT topic naming drafted
- [x] JSON payload mappings drafted
- [x] MQTT QoS policy drafted
- [x] retained/LWT policy drafted
- [x] `/server/snapshot` ROS→HTTP path drafted
- [x] MJPEG/map transport boundary documented
- [x] REST `/api/v1` list drafted
- [x] WebSocket event names drafted
- [x] PostgreSQL 10-table logical schema mapped
- [x] REP-02 PR #2 approved/merged
- [x] P review completed on PR #3
- [x] R1 review completed on PR #3
- [x] R3 review completed on PR #3
- [x] A3 review completed on PR #3

After PR #4 receives final approval and is merged, this `FROZEN v1.0` contract must not change without PM-approved change control.