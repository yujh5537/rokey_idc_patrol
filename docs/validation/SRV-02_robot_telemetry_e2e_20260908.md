# SRV-02 Robot Telemetry E2E Validation

Date: 2026-09-08

## Scope

Validate the SRV-02 telemetry ingestion path from ROS 2 on PC3 through MQTT on PC4, PostgreSQL persistence, and FastAPI robot REST endpoints.

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

Verified REST value:

```text
battery = 0.7900000214576721
battery_percent = 79.0
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

Verified MQTT/REST values:

```text
x   = -0.21974822878837588
y   =  0.02850558981299401
yaw =  2.951612007066097
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

The SRV-02 ingestion pipeline was validated with a ROS 2 test publisher because the actual mission manager publisher was not running during this test. Actual mission-manager integration remains an integration-test item for the MIS owner.

Result: PASS

## Final Result

```text
Battery E2E       PASS
Pose x/y/yaw E2E  PASS
MissionState E2E  PASS
```
