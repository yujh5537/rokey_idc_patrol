#!/usr/bin/env python3

import json
import math

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState


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

        self.get_logger().info(
            f'ROS2 → MQTT Bridge started: '
            f'{self.ros_battery_topic} → '
            f'{self.mqtt_battery_topic} → '
            f'{broker_host}:{broker_port}'
        )

    def battery_callback(self, msg: BatteryState):
        # ROS BatteryState percentage는 0.0 ~ 1.0
        if math.isfinite(msg.percentage) and msg.percentage >= 0.0:
            battery_percent = round(float(msg.percentage) * 100.0, 1)
        else:
            battery_percent = None

        payload = {
            'robot_id': self.robot_id,
            'battery_percent': battery_percent,
            'voltage': round(float(msg.voltage), 3),
            'temperature': round(float(msg.temperature), 2),
            'present': bool(msg.present),
            'stamp': {
                'sec': msg.header.stamp.sec,
                'nanosec': msg.header.stamp.nanosec,
            },
        }

        payload_json = json.dumps(
            payload,
            ensure_ascii=False
        )

        result = self.mqtt_client.publish(
            self.mqtt_battery_topic,
            payload_json
        )

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
