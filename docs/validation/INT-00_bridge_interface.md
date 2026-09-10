# INT-00 bridge interface — #12 W contact

## Scope and source

- Base: main `4bc833b` (merged #9 / #12 message and event implementation).
- Fix branch: `euiseok/20260910-int00-bridge-interface`.
- Integration branch: `euiseok/20260910-srv03-int00-integration`, combining the
  fix with `euiseok/20260908-srv03-rack-layout` without rewriting that branch.
- MissionState: `rack_idx`, `rack_total`, `zone_id`, `expected_rack_id`.
- SecurityEvent: global `/event/events` → `idc/events/security`, including
  `basis`, `open_ratio`, `frames`, `marker_checked`, identity, position and stamp.
- No ROS message definitions, Vision judgement, rack coordinates or navigation
  behaviour are changed by this bridge patch.
- Attached v1.4 Word documents still describe some pre-REP-03 fields. For this
  requested contact, the merged `.msg` files and #12 supersede those stale fields.

## Automated verification

```bash
python3 -m unittest discover -s src/idc_web/idc_bridge/test -v
```

13 offline tests passed using the checked-out `.msg` field lists, fake ROS/MQTT
I/O and real SQLite persistence. Covers both E5 bases, native field types, both
robot bridges, PUBACK ordering, disconnect during publish, queue rejection,
restart/FIFO/time preservation, JSON NaN/Inf handling, battery and pose regression.
This is not a live ROS/DDS, Paho-network or robot integration test.

## PC3 deployment

From the repository root, stop existing bridge processes before restarting.
Use the site's existing ROS discovery configuration.

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select idc_msgs idc_bridge
source install/setup.bash
ros2 interface show idc_msgs/msg/MissionState
ros2 interface show idc_msgs/msg/SecurityEvent
```

Run one bridge per terminal (existing battery/pose remaps preserved):

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -r /tf:=/robot5/tf -r /tf_static:=/robot5/tf_static
```

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot11 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883 \
  -r /tf:=/robot11/tf -r /tf_static:=/robot11/tf_static
```

Do not run two bridge instances for the same robot. SQLite outboxes live outside
the repository under `~/.ros/idc_bridge/`. Do not delete an outbox during an outage.

## Field acceptance (pending)

1. On PC4, observe the broker before producing events:

   ```bash
   mosquitto_sub -h 192.168.107.124 -p 1883 \
     -t 'idc/+/mission/state' -t 'idc/events/security' -v
   ```

2. With the site's real MissionState publisher, confirm INSPECT/MARKER_CHECK,
   rack_idx/rack_total and expected_rack_id in MQTT. No waypoint attribute error.
3. Observe `/event/events` alongside MQTT. For robot5 and robot11 independently,
   confirm one normal-path MQTT publication per source event and exact four
   diagnostic fields for both `yolo` and `marker_missing` results.
4. During a coordinated broker outage, confirm events queue and replay after
   reconnect with unchanged source/receive timestamps. Repeat with bridge restart.
   QoS 1 replay is possible; this is not an exactly-once promise.
5. Check battery and pose still arrive. Record ROS publish and MQTT receive time.

Use mock mission/events only in an isolated ROS test graph: mission state also
feeds other robot nodes. Do not inject test state into the active patrol graph.

## Remaining INT-00 stages

- PC4 main's MQTT consumer currently subscribes only to battery/state/pose.
  Security-event DB ingestion and `event_new` WebSocket delivery are not added
  by this contact patch. Broker receipt must not be reported as full Web delivery.
- Rack branch currently contains demo events and pose-only WebSocket messages.
  Confirm the separate backend/UI event implementation before scheduling full
  ROS → MQTT → DB → browser acceptance.
- #12 annotated image transport path is
  `/robotN/perception/image_annotated/compressed`. No direct annotated-image
  subscriber exists in the inspected `src/idc_web` code, so no unrelated image
  subscription is added here. Future direct CompressedImage subscribers use it.
- Actual robot, broker disconnect/restart, PostgreSQL and browser timing gates
  remain pending at the deployment PCs.
