# ADR-001 — Split ROS Control and Web Control Planes

- Status: **ACCEPTED**
- Date: 2026-09-06
- Owner: W
- Related task: SRV-00
- Related contract: `docs/mqtt_interface_v1.md`
- ROS interface baseline: REP-02 PR #2

## 1. Context

The original SDD v1.0 describes a single control-server process that combines ROS 2 (`rclpy`), Flask/SocketIO, and SQLite on the control PC. The current implementation plan has changed because the deployment now separates the ROS control machine and the Web/control-server machine.

Current deployment baseline:

```text
TurtleBot4 / ROS 2 graph
  /robot5
  /robot11
      │
      ▼
PC3 Main / Control PC
192.168.107.21
  - ROS 2 Jazzy
  - Fast DDS Discovery Server ID 0
  - SLAM / Nav2 / mission / event ROS nodes
  - idc_bridge (ROS↔Web boundary)
      │
      ├─ MQTT telemetry / commands
      ├─ HTTP snapshot upload
      ├─ SSH/rsync map files
      └─ MJPEG camera stream
      │
      ▼
PC4 Web PC
192.168.107.124
  - Mosquitto
  - FastAPI
  - PostgreSQL
  - React
  - No ROS 2 dependency
```

This ADR records that architecture decision so later SRV/BRG implementation does not drift back to the old Flask+rclpy single-process design.

## 2. Decision

### 2.1 Separate the ROS control plane from the Web/data plane

PC3 owns all ROS 2 participation and all ROS-side service/action calls.

PC4 is ROS-free and communicates with PC3 only through explicit network contracts.

### 2.2 PC3 responsibilities

PC3 owns:

- Fast DDS Discovery Server and ROS 2 graph participation.
- Robot namespaces `/robot5` and `/robot11`.
- ROS topic subscription for battery, mission state, pose, nav status, perception/event messages as needed.
- MQTT publication of selected telemetry/events.
- MQTT subscription for browser-originated commands and translation to ROS services/actions.
- `/server/snapshot` ROS service implementation at the boundary, with HTTP forwarding to PC4.
- Local retry queue for broker/network outages.
- `web_video_server` for MJPEG camera delivery.
- Map file production and SSH/rsync transfer to PC4.

Implementation ownership boundary for PC3 integration:

- W owns `idc_bridge` code and bridge parameters.
- R1 owns PC3 integrated launch/respawn orchestration under INF-07, with W as secondary/support owner for bridge integration.

### 2.3 PC4 responsibilities

PC4 owns:

- Mosquitto MQTT broker.
- FastAPI REST API.
- PostgreSQL operational database.
- React dashboard.
- Browser WebSocket fan-out.
- Evidence image storage and SHA-256 calculation.
- Audit-log persistence and verification.
- REST-command publication into MQTT.

PC4 must not import `rclpy`, subscribe directly to ROS topics, or depend on ROS package discovery.

## 3. Transport decisions

Different data classes use different transports.

| Data | Transport | Reason |
|---|---|---|
| Battery / mission state / pose / nav status | MQTT | small realtime telemetry, decoupled from ROS |
| Security events | MQTT QoS 1 + bridge retry queue | event delivery must survive temporary broker loss |
| Browser commands | REST → MQTT → ROS | browser stays ROS-agnostic; `request_id` gives correlation/idempotency |
| Snapshot/evidence JPEG | ROS service → HTTP multipart upload | binary evidence should not be carried in MQTT |
| Map YAML/PGM | SSH/rsync | map artifacts are files, not realtime messages |
| Camera live view | MJPEG from PC3 | avoid broker/database load from video frames |
| Browser realtime updates | WebSocket from PC4 | efficient push without polling |

## 4. MQTT policy

The detailed contract lives in `docs/mqtt_interface_v1.md`. This ADR fixes the architecture principles:

- Topic prefix: `idc/{robot}/...`.
- `{robot}` is namespace without the leading slash.
- Current values are `robot5` and `robot11`; code must remain configurable.
- Pose/high-rate disposable telemetry may use MQTT QoS 0.
- Events, state transitions, and commands use MQTT QoS 1.
- Dynamic data is not retained.
- Only `idc/{robot}/bridge/status` uses retained messages and MQTT Last Will.
- Commands require `request_id` and duplicate suppression in the bridge.

## 5. REP-02 ownership boundary

REP-02 is the ROS contract owned by P and frozen after review.

W must not rename, remove, or reinterpret REP-02 fields. The bridge may add transport-only metadata such as:

- `schema_version`
- `received_at`
- `request_id`

These fields exist only at the Web/MQTT boundary and do not alter ROS `.msg/.srv` definitions.

`MissionState.msg` intentionally has no Header in REP-02. The bridge therefore records PC3 receive time as `received_at` instead of changing the ROS message.

## 6. Snapshot decision

`/server/snapshot` remains a ROS service for R3/MIS-05, but the service implementation lives on PC3, not PC4.

```text
mission_manager
  → ROS /server/snapshot
  → PC3 idc_bridge snapshot_service
  → HTTP POST /api/v1/evidence
  → PC4 FastAPI
  → PostgreSQL + file storage + SHA-256
  → HTTP response
  → ROS Snapshot response
```

This preserves the REP-02 service interface while keeping PC4 ROS-free.

## 7. Database decision

The logical database contract remains the SRD 10-table set:

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

Primary implementation: PostgreSQL on PC4.

Application persistence is implemented through SQLAlchemy so an approved SQLite fallback can use the same model layer by changing `DATABASE_URL` rather than rewriting application logic.

The canonical rack identifier contract is defined in `docs/mqtt_interface_v1.md`: `rack_id` is `R01`...`R56`, with `aruco_id = int(rack_id[1:])`.

## 8. Consequences

### Positive

- Web PC is isolated from ROS/DDS configuration and failures.
- Browser/backend can be tested without physical robots using MQTT fixtures.
- ROS-side integration can be tested without running the React frontend.
- Transport bandwidth is controlled by data type.
- PC3 can queue important event data during temporary PC4/broker outages.
- FastAPI/PostgreSQL can be deployed/restarted independently from Nav2/SLAM.
- The architecture better matches module independence required by SR-Q11.

### Negative / cost

- Additional bridge code is required.
- MQTT/HTTP contracts must be versioned and reviewed.
- Two-machine time synchronization and failure handling become explicit concerns.
- More integration tests are required than with a single in-process Flask+rclpy server.

These costs are accepted because they produce a cleaner ROS/Web boundary and reduce deployment coupling.

## 9. Rejected alternatives

### Alternative A — Flask/SocketIO + rclpy + SQLite in one PC/process

Rejected for the current v3 implementation because:

- PC4 would have to participate in ROS or the Web stack would have to remain on PC3.
- Backend restarts could interfere with ROS communication.
- ROS and browser concerns remain tightly coupled.
- It conflicts with the current PC3/PC4 physical deployment.

### Alternative B — Send all data through MQTT

Rejected because images/video/maps are large binary/file workloads. MQTT is reserved for control and compact state/event data.

### Alternative C — Browser talks directly to ROS/WebSocket bridge

Rejected because SRD requires a versioned REST/WebSocket server boundary and the browser must not depend on robot-internal ROS nodes.

## 10. Failure handling principles

- Broker disconnect: bridge reconnects; critical events remain in local queue and are retried.
- PC4 backend down: robot-side ROS mission remains independent; Web data path reports unavailable.
- PC3 bridge down: retained `bridge/status` LWT marks the robot bridge offline.
- Stale telemetry: UI must show stale/offline using receive timestamps rather than pretending cached values are live.
- Duplicate MQTT QoS 1 command: bridge deduplicates using `request_id`.
- Invalid command payload: reject and publish/return an explicit failure result.

## 11. Security and data rules

- Deployment is internal LAN only for Phase 1.
- Raw patrol video is not stored.
- Evidence is stored only through the evidence endpoint and receives SHA-256 metadata.
- Original evidence access and management actions are recorded by the audit subsystem in later SRV work.
- Secrets, passwords, and machine-specific absolute paths must not be committed to source.

## 12. Migration impact on existing documents/code

The following old SDD assumptions are superseded by this ADR for the current implementation and must be corrected later in DOC-02:

- Flask → FastAPI.
- Flask-SocketIO → FastAPI WebSocket.
- SQLite primary DB → PostgreSQL primary DB (SQLite fallback allowed).
- `control_server(Flask+SocketIO+rclpy)` → PC3 `idc_bridge` + PC4 FastAPI.
- Old `/robot1`, `/robot2` examples → deployment `/robot5`, `/robot11` while keeping code namespace-configurable.
- Old ROS domain/network/IP examples → current as-built network values.

Runtime prerequisites requested in the R1 review (Discovery/SUPER_CLIENT details and the INF-01 time-synchronization value) may be documented in a follow-up runtime-prerequisites PR because they do not change this frozen transport contract.

## 13. Review / acceptance checklist

ADR-001 becomes **ACCEPTED** only when the following review work is complete. Review completion is recorded on PR #3; PR #4 is the final freeze/acceptance PR.

- [x] P reviewed the architecture and REP-02 boundary.
- [x] R1 reviewed PC3 ROS/Discovery/telemetry inputs and launch ownership.
- [x] R3 reviewed command and `/server/snapshot` call flow.
- [x] A3 reviewed `SecurityEvent` publication path and rack-id convention.
- [x] `docs/mqtt_interface_v1.md` was reviewed together with this ADR.

After PR #4 receives final Code Owner approval and is merged, ADR-001 is accepted together with `mqtt_interface_v1.md` FROZEN v1.0. Further contract changes require PM-approved change control.
