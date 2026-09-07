#!/usr/bin/env python3

from datetime import datetime, timezone
import json
import math

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState


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


class MqttBridge(Node):

    def __init__(self):
        super().__init__('mqtt_bridge')

        # 실행할 때 주입하는 설정값
        self.declare_parameter('robot_namespace', '')
        self.declare_parameter('mqtt_broker_host', '192.168.107.124')
        self.declare_parameter('mqtt_broker_port', 1883)

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

        if not robot_namespace:
            raise ValueError(
                'robot_namespace parameter is required. '
                'Example: -p robot_namespace:=/robot5'
            )

        self.robot_id = robot_namespace

        # ROS2와 MQTT에서 사용할 Topic
        self.ros_battery_topic = f'/{self.robot_id}/battery_state'
        self.mqtt_battery_topic = f'idc/{self.robot_id}/battery'

        # 최신 ROS BatteryState를 MQTT 1 Hz로 재전송하기 위한 캐시.
        # received_at/stamp는 새 ROS 메시지를 받은 시점의 값을 그대로 보존한다.
        self.latest_battery_payload = None

        # MQTT Client
        self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f'idc-{self.robot_id}-bridge'
        )

        self.mqtt_client.connect(
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

        # FROZEN MQTT Interface v1 §3: battery publish rate >= 1 Hz.
        # 로봇 BatteryState source가 더 느려도 최신 값을 1 Hz로 전달하고,
        # freshness 판단은 보존된 received_at/stamp로 수행한다.
        self.battery_publish_timer = self.create_timer(
            1.0,
            self.publish_battery,
        )

        self.get_logger().info(
            f'ROS2 → MQTT Bridge started: '
            f'{self.ros_battery_topic} → '
            f'{self.mqtt_battery_topic} → '
            f'{broker_host}:{broker_port} (battery publish: 1 Hz)'
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

        # FROZEN common JSON rule: NaN/Inf를 JSON 숫자로 내보내지 않는다.
        payload_json = json.dumps(
            self.latest_battery_payload,
            ensure_ascii=False,
            allow_nan=False,
        )

        # FROZEN topic contract: battery QoS 1, retain false, rate >= 1 Hz.
        result = self.mqtt_client.publish(
            self.mqtt_battery_topic,
            payload_json,
            qos=1,
            retain=False,
        )

        battery_percent = self.latest_battery_payload['battery_percent']
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self.get_logger().info(
                f'published {self.mqtt_battery_topic}: '
                f'{battery_percent}%'
            )
        else:
            self.get_logger().error(
                f'MQTT publish failed: rc={result.rc}'
            )

    def destroy_node(self):
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
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
