# SRV-02 Robot Telemetry E2E Validation

Date: 2026-09-08

## Scope

Validate the SRV-02 telemetry ingestion path from ROS 2 on PC3 through MQTT on PC4, PostgreSQL persistence, and FastAPI robot/event REST endpoints.

## Environment

- PC3: ROS 2 Jazzy, `idc_bridge`, TurtleBot4 `robot5`
- PC4: Mosquitto, FastAPI, PostgreSQL
- MQTT broker: `192.168.107.124:1883`

## Battery

Path:

```text
/robot5/battery_state
→ idc_bridge
→ idc/robot5/battery
→ PC4 MQTT consumer
→ PostgreSQL robots
→ GET /api/v1/robots/robot5
```

Initial verified REST value:

```text
battery = 0.7900000214576721
battery_percent = 79.0
```

Fresh-process revalidation after restarting the SRV-02 stack:

```text
battery = 0.5799999833106995
battery_percent = 58.0
```

Result: PASS

## Pose

Path:

```text
map → base_link TF
→ idc_bridge
→ idc/robot5/pose
→ PC4 MQTT consumer
→ PostgreSQL robots
→ GET /api/v1/robots/robot5
```

Initial verified MQTT/REST values:

```text
x   = -0.21974822878837588
y   =  0.02850558981299401
yaw =  2.951612007066097
```

Fresh-process revalidation:

```text
x   = -0.2366471433526262
y   = -0.002322829883354807
yaw =  3.101208521429405
```

`idc/robot5/pose` was observed at approximately 2 Hz.

Result: PASS

## Mission State

Path:

```text
/robot5/mission/state
→ idc_bridge
→ idc/robot5/mission/state
→ PC4 MQTT consumer
→ PostgreSQL robots.state
→ GET /api/v1/robots/robot5
```

Validation message:

```text
robot_id = robot5
state = PATROL
waypoint_idx = 0
waypoint_total = 10
note = SRV02_E2E_TEST
```

Verified REST value:

```text
state = PATROL
```

The fresh-process revalidation also returned `state = PATROL` from `GET /api/v1/robots/robot5`.

The SRV-02 ingestion pipeline was validated with a ROS 2 test publisher because the actual mission manager publisher was not running during this test. Actual mission-manager integration remains an integration-test item for the MIS owner.

Result: PASS

## Events REST

SRV-00 reserves `GET /api/v1/events` for event list/filter. SRV-02 implements the minimum read path without moving SRV-04/SRV-05 event ingestion, evidence, or ACK responsibilities into this task.

Implemented endpoint:

```http
GET /api/v1/events
```

Supported optional filters:

```text
type
status
robot_id
rack_id
zone_id
limit (1..500, default 100)
```

Response fields preserve the existing `events` DB schema, including `detail_json` as a string.

Code-level contract validation:

```text
- newest event ordering: PASS
- type + robot_id filtering: PASS
- invalid limit validation: PASS (HTTP 422)
```

PC4 runtime log confirmed:

```text
GET /api/v1/events HTTP/1.1 200 OK
```

Result: PASS

## REST Response-Time Validation

SRV-02 target:

```text
API response < 1.0 second
```

Runtime validation command executed on PC4:

```bash
bash docs/validation/SRV-02_api_runtime_check.sh
```

Observed PC4 output:

```text
robots API         HTTP 200  0.003355s  http://127.0.0.1:8000/api/v1/robots
robot detail API   HTTP 200  0.002503s  http://127.0.0.1:8000/api/v1/robots/robot5
events API         HTTP 200  0.003848s  http://127.0.0.1:8000/api/v1/events
PASS: all SRV-02 REST endpoints returned 2xx in under 1.0s
```

Measured values:

```text
GET /api/v1/robots         0.003355 s  PASS
GET /api/v1/robots/robot5  0.002503 s  PASS
GET /api/v1/events         0.003848 s  PASS
```

All measured endpoints returned HTTP 200 and remained well below the 1.0 second SRV-02 requirement.

Result: PASS

## Final Result

```text
Battery E2E                  PASS
Pose x/y/yaw E2E             PASS
MissionState E2E             PASS
GET /api/v1/events contract  PASS
GET /api/v1/events runtime   PASS
REST response < 1.0 s        PASS
```

SRV-02 completion criteria covered by this task are satisfied. Actual `mission_manager` publisher integration remains a later MIS integration-test item and does not block the SRV-02 ingestion-path sign-off.
