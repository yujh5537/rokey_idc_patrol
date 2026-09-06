# MQTT Interface v1 — IDC Patrol Control/Web Boundary

> Status: **DRAFT — P·R1·R3·A3 review required before Freeze**  
> Owner: W (Control Server / Web UI / ROS↔Web boundary)  
> Date: 2026-09-06  
> Related task: SRV-00  
> ROS interface baseline: REP-02 PR #2 (`yujh5537/20260906-msgs-idc-interface-v1`)

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
| ROS→Web | `idc/{robot}/nav/status` | Nav2 action/status summary | 1 | false | on change |
| ROS→Web | `idc/{robot}/perception/objects` | `/robotN/perception/objects` (`idc_msgs/ObjectArray`) | 0 | false | up to 10 Hz; default Web forwarding OFF unless needed |
| ROS→Web | `idc/events/security` | `/event/events` (`idc_msgs/SecurityEvent`) | 1 | false | event |
| Web→ROS | `idc/{robot}/cmd/nav_goal` | Nav2 `NavigateToPose` | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/dock` | Create3 dock action | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/undock` | Create3 undock action | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/stop` | mission/nav safe stop path | 1 | false | command |
| Web→ROS | `idc/{robot}/cmd/mission` | mission manager start/stop/return | 1 | false | command |
| ROS→Web | `idc/{robot}/cmd/result` | bridge command result | 1 | false | result |
| Bridge | `idc/{robot}/bridge/status` | bridge availability / LWT | 1 | **true** | connect/disconnect |

### Retained policy

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

REP-02 fields are preserved exactly; no ROS interface field is added by the bridge.

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "state": "PATROL",
  "waypoint_idx": 2,
  "waypoint_total": 8,
  "battery": 0.71,
  "note": "",
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

`MissionState.msg` has no Header in REP-02/SDD 4.2.3, so MQTT `received_at` is the PC3 bridge receive time.

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
      "zone_id": "zone-a",
      "rack_id": "rack-01",
      "identity": ""
    }
  ],
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

This stream can be high-rate; default PC4 forwarding is OFF unless UI/debug requires it. Event detection remains on the ROS side.

### 4.5 SecurityEvent → `idc/events/security`

```json
{
  "schema_version": "1.0",
  "robot_id": "robot5",
  "type": "E5",
  "severity": 3,
  "zone_id": "zone-a",
  "rack_id": "rack-01",
  "position": {"x": 1.0, "y": 2.0, "z": 0.0},
  "evidence_ids": [101],
  "detail_json": "{\"votes\":12,\"frames\":15}",
  "stamp": {"sec": 0, "nanosec": 0},
  "received_at": "2026-09-06T07:00:00.000Z"
}
```

- `detail_json` remains a JSON **string** because REP-02 defines it as `string`; the bridge must not silently change its type.
- MQTT QoS 1; event messages are not retained.
- PC3 bridge must queue unsent events locally during broker outage and retry after reconnect (BRG-03).

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

Minimum v1 resources required by SRD/SRV work:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | backend/database/broker health |
| GET | `/api/v1/robots` | robot cards/state |
| GET | `/api/v1/robots/{robot_id}` | one robot state |
| POST | `/api/v1/robots/{robot_id}/commands` | publish MQTT command, return `request_id` |
| GET | `/api/v1/events` | event list/filter |
| GET | `/api/v1/events/{event_id}` | event detail |
| POST | `/api/v1/events/{event_id}/ack` | operator ACK + audit log |
| POST | `/api/v1/evidence` | snapshot image + metadata → evidence_id |
| GET | `/api/v1/maps/current` | current merged-map metadata |
| GET | `/api/v1/patrol-runs` | patrol history |
| GET/PUT | `/api/v1/waypoints` | patrol route read/update |
| GET/PUT | `/api/v1/zones` | zone/policy read/update |
| GET | `/api/v1/racks` | rack metadata |
| GET/POST/DELETE | `/api/v1/persons` | authorised-person records (optional feature) |
| GET/POST | `/api/v1/auth-events` | virtual auth events |
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

Baseline columns are inherited from SDD 4.2.4:

- `robots(id, name, last_seen, battery, state, x, y, yaw)`
- `patrol_runs(id, started_at, ended_at, map_id, coverage, status)`
- `waypoints(id, run_id, robot_id, seq, x, y, yaw, rack_id, visited_at, result)`
- `zones(id, name, polygon_json, allowed_from, allowed_to, min_persons, max_dwell_sec, allowed_person_ids)`
- `racks(id, aruco_id, x, y, yaw, zone_id, baseline_door, baseline_led)`
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

## 11. REP-02 review notes before Freeze

The schemas are usable from the W boundary perspective, with two documentation comments to correct before/at merge:

1. `ObjectArray.msg` comment currently examples `robot1 | robot2`; current deployment is `robot5 | robot11`. Prefer a generic rule: `robot_id = namespace without leading slash`.
2. `Snapshot.srv`/event/mission comments still describe the old direct `control_server` ROS consumer/server. In v3, PC3 `idc_bridge` owns the ROS boundary and PC4 is ROS-free. This is a comment/ownership correction; message/service fields do not need to change.

`MissionState.msg` intentionally follows SDD 4.2.3 and has no Header; the bridge adds `received_at` rather than changing REP-02.

## 12. Freeze checklist

SRV-00 is complete only after all are checked:

- [x] MQTT topic naming drafted
- [x] JSON payload mappings drafted
- [x] MQTT QoS policy drafted
- [x] retained/LWT policy drafted
- [x] `/server/snapshot` ROS→HTTP path drafted
- [x] MJPEG/map transport boundary documented
- [x] REST `/api/v1` list drafted
- [x] WebSocket event names drafted
- [x] PostgreSQL 10-table logical schema mapped
- [ ] REP-02 PR #2 approved/merged
- [ ] P review approved
- [ ] R1 review approved
- [ ] R3 review approved
- [ ] A3 review approved

After the four interface reviews, change this document status from `DRAFT` to `FROZEN v1.0`. Do not change the frozen contract without PM-approved change control.
