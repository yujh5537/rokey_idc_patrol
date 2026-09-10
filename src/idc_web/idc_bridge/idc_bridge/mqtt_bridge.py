#!/usr/bin/env python3

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from queue import Empty, SimpleQueue
import re

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import BatteryState
from tf2_ros import Buffer, TransformException, TransformListener

from idc_msgs.msg import MissionState, SecurityEvent
from idc_bridge.event_outbox import EventOutbox


def _finite_or_none(value, digits=None):
    """Return a finite JSON-safe float, otherwise None."""
    value = float(value)
    if not math.isfinite(value):
        return None
    if digits is not None:
        return round(value, digits)
    return value


def _received_at_utc():
    """PC3 bridge receive time in UTC ISO-8601 with millisecond precision."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )


def _yaw_from_quaternion(x, y, z, w):
    """Return planar yaw (radians) from a quaternion."""
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


class MqttBridge(Node):

    def __init__(self):
        super().__init__('mqtt_bridge')

        # 실행할 때 주입하는 설정값
        self.declare_parameter('robot_namespace', '')
        self.declare_parameter('mqtt_broker_host', '192.168.107.124')
        self.declare_parameter('mqtt_broker_port', 1883)
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('event_queue_path', '')

        robot_namespace = (
            self.get_parameter('robot_namespace')
            .get_parameter_value()
            .string_value
            .strip('/')
        )

        broker_host = (
            self.get_parameter('mqtt_broker_host')
            .get_parameter_value()
            .string_value
        )

        broker_port = (
            self.get_parameter('mqtt_broker_port')
            .get_parameter_value()
            .integer_value
        )

        self.map_frame = (
            self.get_parameter('map_frame')
            .get_parameter_value()
            .string_value
            .strip('/')
        )

        self.base_frame = (
            self.get_parameter('base_frame')
            .get_parameter_value()
            .string_value
            .strip('/')
        )

        if not robot_namespace:
            raise ValueError(
                'robot_namespace parameter is required. '
                'Example: -p robot_namespace:=/robot5'
            )

        if not re.fullmatch(r'[A-Za-z0-9_-]+', robot_namespace):
            raise ValueError('robot_namespace must be a single robot identifier')

        if not self.map_frame:
            raise ValueError('map_frame parameter must not be empty')

        if not self.base_frame:
            raise ValueError('base_frame parameter must not be empty')

        self.robot_id = robot_namespace

        # TurtleBot4의 /robotN/tf topic 안 frame_id는 namespace 없이
        # odom/base_link를 사용한다. MQTT 계약에서는 로봇별 식별을 위해
        # logical child_frame_id를 robotN/base_link 형태로 유지한다.
        self.pose_child_frame_id = f'{self.robot_id}/{self.base_frame}'

        # ROS2와 MQTT에서 사용할 Topic
        self.ros_battery_topic = f'/{self.robot_id}/battery_state'
        self.ros_mission_state_topic = f'/{self.robot_id}/mission/state'
        self.mqtt_battery_topic = f'idc/{self.robot_id}/battery'
        self.mqtt_mission_state_topic = f'idc/{self.robot_id}/mission/state'
        self.mqtt_pose_topic = f'idc/{self.robot_id}/pose'
        self.ros_security_event_topic = '/event/events'
        self.mqtt_security_event_topic = 'idc/events/security'
        queue_path = self.get_parameter('event_queue_path').value or (
            Path.home() / '.ros' / 'idc_bridge' / f'{self.robot_id}-events.sqlite3'
        )
        self.event_outbox = EventOutbox(queue_path)
        self.event_inflight = None
        self.event_acks = SimpleQueue()

        # 최신 ROS BatteryState를 MQTT 1 Hz로 재전송하기 위한 캐시.
        # received_at/stamp는 새 ROS 메시지를 받은 시점의 값을 그대로 보존한다.
        self.latest_battery_payload = None

        # MQTT Client
        self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f'idc-{self.robot_id}-bridge'
        )
        self.mqtt_client.on_publish = self._on_mqtt_publish

        self.mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        # A broker outage at startup must not stop ROS event collection.
        self.mqtt_client.connect_async(
            broker_host,
            broker_port,
            keepalive=60
        )

        self.mqtt_client.loop_start()

        # ROS2 BatteryState Subscriber
        self.battery_subscription = self.create_subscription(
            BatteryState,
            self.ros_battery_topic,
            self.battery_callback,
            qos_profile_sensor_data
        )

        # ROS2 MissionState Subscriber — FROZEN contract 2 Hz source.
        self.mission_state_subscription = self.create_subscription(
            MissionState,
            self.ros_mission_state_topic,
            self.mission_state_callback,
            10,
        )

        self.security_event_subscription = self.create_subscription(
            SecurityEvent,
            self.ros_security_event_topic,
            self.security_event_callback,
            10,
        )
        self.event_publish_timer = self.create_timer(0.1, self.publish_pending_event)

        # TF map -> base_link pose bridge.
        # /robotN/tf와 /robotN/tf_static은 실행 시 remap해서 로봇별로 격리한다.
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # FROZEN MQTT Interface v1 §3: battery publish rate >= 1 Hz.
        # 로봇 BatteryState source가 더 느려도 최신 값을 1 Hz로 전달하고,
        # freshness 판단은 보존된 received_at/stamp로 수행한다.
        self.battery_publish_timer = self.create_timer(
            1.0,
            self.publish_battery,
        )

        # FROZEN MQTT Interface v1 §3/§4.3: pose publish rate 2 Hz.
        self.pose_publish_timer = self.create_timer(
            0.5,
            self.publish_pose,
        )

        self.get_logger().info(
            f'ROS2 → MQTT Bridge started: '
            f'battery={self.ros_battery_topic} → {self.mqtt_battery_topic} (1 Hz), '
            f'mission={self.ros_mission_state_topic} → {self.mqtt_mission_state_topic}, '
            f'events={self.ros_security_event_topic} → {self.mqtt_security_event_topic} '
            f'(robot_id={self.robot_id}), '
            f'pose={self.map_frame}→{self.base_frame} '
            f'(logical child={self.pose_child_frame_id}) → {self.mqtt_pose_topic} (2 Hz), '
            f'broker={broker_host}:{broker_port}'
        )

    def _publish_json(self, topic, payload, *, qos):
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
        )

        return self.mqtt_client.publish(
            topic,
            payload_json,
            qos=qos,
            retain=False,
        )

    def battery_callback(self, msg: BatteryState):
        # FROZEN v1.0 §4.1: BatteryState percentage 정본은 0.0 ~ 1.0.
        raw_percentage = float(msg.percentage)
        if math.isfinite(raw_percentage) and 0.0 <= raw_percentage <= 1.0:
            percentage = raw_percentage
            battery_percent = round(percentage * 100.0, 1)
        else:
            percentage = None
            battery_percent = None

        # docs/mqtt_interface_v1.md §2, §3, §4.1 계약을 그대로 따른다.
        # received_at은 ROS 메시지를 PC3 bridge가 실제로 받은 시각이다.
        self.latest_battery_payload = {
            'schema_version': '1.0',
            'robot_id': self.robot_id,
            'battery_percent': battery_percent,
            'percentage': percentage,
            'voltage': _finite_or_none(msg.voltage, 3),
            'temperature': _finite_or_none(msg.temperature, 2),
            'present': bool(msg.present),
            'stamp': {
                'sec': msg.header.stamp.sec,
                'nanosec': msg.header.stamp.nanosec,
            },
            'received_at': _received_at_utc(),
        }

    def publish_battery(self):
        if self.latest_battery_payload is None:
            return

        # FROZEN topic contract: battery QoS 1, retain false, rate >= 1 Hz.
        result = self._publish_json(
            self.mqtt_battery_topic,
            self.latest_battery_payload,
            qos=1,
        )

        battery_percent = self.latest_battery_payload['battery_percent']
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().info(
                f'published {self.mqtt_battery_topic}: '
                f'{battery_percent}%'
            )
        else:
            self.get_logger().error(
                f'MQTT battery publish failed: rc={result.rc}'
            )

    def mission_state_callback(self, msg: MissionState):
        msg_robot_id = msg.robot_id.strip('/')
        if msg_robot_id != self.robot_id:
            self.get_logger().warning(
                f'ignored MissionState robot_id mismatch: '
                f'topic={self.robot_id} payload={msg.robot_id!r}'
            )
            return

        battery = _finite_or_none(msg.battery)
        if battery is not None and not 0.0 <= battery <= 1.0:
            battery = None

        payload = {
            'schema_version': '1.0',
            'robot_id': msg_robot_id,
            'state': msg.state,
            'zone_id': msg.zone_id,
            'expected_rack_id': msg.expected_rack_id,
            'rack_idx': int(msg.rack_idx),
            'rack_total': int(msg.rack_total),
            'battery': battery,
            'note': msg.note,
            'received_at': _received_at_utc(),
        }

        result = self._publish_json(
            self.mqtt_mission_state_topic,
            payload,
            qos=1,
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().error(
                f'MQTT mission state publish failed: rc={result.rc}'
            )

    def security_event_callback(self, msg: SecurityEvent):
        # /event/events is global. Each robot bridge owns only its robot's events.
        # Preserve the source robot_id; never relabel another robot's event.
        if msg.robot_id != self.robot_id:
            return

        payload = {
            'schema_version': '1.0',
            'robot_id': msg.robot_id,
            'type': msg.type,
            'zone_id': msg.zone_id,
            'rack_id': msg.rack_id,
            'position': {
                'x': _finite_or_none(msg.position.x),
                'y': _finite_or_none(msg.position.y),
                'z': _finite_or_none(msg.position.z),
            },
            'basis': msg.basis,
            'open_ratio': _finite_or_none(msg.open_ratio),
            'frames': int(msg.frames),
            'marker_checked': bool(msg.marker_checked),
            'stamp': {
                'sec': msg.header.stamp.sec,
                'nanosec': msg.header.stamp.nanosec,
            },
            'received_at': _received_at_utc(),
        }
        # Persist before sending. Retrying preserves the original timestamps.
        self.event_outbox.enqueue(payload)
        self.publish_pending_event()

    def _on_mqtt_publish(self, client, userdata, mid, reason_code, properties):
        # MQTT network thread: hand off PUBACKs; do not touch SQLite here.
        if not getattr(reason_code, 'is_failure', False):
            self.event_acks.put(mid)

    def publish_pending_event(self):
        while True:
            try:
                mid = self.event_acks.get_nowait()
            except Empty:
                break
            if self.event_inflight is not None:
                row_id, event_mid = self.event_inflight
                if mid == event_mid:
                    self.event_outbox.acknowledge(row_id)
                    self.event_inflight = None

        if self.event_inflight is not None:
            # Paho retries its in-flight QoS 1 message after reconnect.
            return

        if not self.mqtt_client.is_connected():
            return
        row = self.event_outbox.peek()
        if row is None:
            return
        row_id, encoded = row
        info = self.mqtt_client.publish(
            self.mqtt_security_event_topic, encoded, qos=1, retain=False,
        )
        # NO_CONN for QoS 1 is still queued by Paho. Keep the same message ID
        # instead of enqueuing duplicates on every timer tick.
        if info.rc in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN):
            self.event_inflight = (row_id, info.mid)
        else:
            self.get_logger().error(f'MQTT event publish failed: rc={info.rc}')

    def publish_pose(self):
        try:
            transform = self.tf_buffer.lookup_transform(
                self.map_frame,
                self.base_frame,
                Time(),
            )
        except TransformException:
            # TF가 아직 준비되지 않은 startup/localization 구간은 정상적인 상태다.
            return

        translation = transform.transform.translation
        rotation = transform.transform.rotation

        x = _finite_or_none(translation.x)
        y = _finite_or_none(translation.y)
        yaw = _finite_or_none(
            _yaw_from_quaternion(
                rotation.x,
                rotation.y,
                rotation.z,
                rotation.w,
            )
        )

        if x is None or y is None or yaw is None:
            self.get_logger().warning('ignored non-finite TF pose')
            return

        payload = {
            'schema_version': '1.0',
            'robot_id': self.robot_id,
            'frame_id': self.map_frame,
            'child_frame_id': self.pose_child_frame_id,
            'x': x,
            'y': y,
            'yaw': yaw,
            'stamp': {
                'sec': transform.header.stamp.sec,
                'nanosec': transform.header.stamp.nanosec,
            },
            'received_at': _received_at_utc(),
        }

        result = self._publish_json(
            self.mqtt_pose_topic,
            payload,
            qos=0,
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().error(
                f'MQTT pose publish failed: rc={result.rc}'
            )

    def destroy_node(self):
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.event_outbox.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = MqttBridge()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
