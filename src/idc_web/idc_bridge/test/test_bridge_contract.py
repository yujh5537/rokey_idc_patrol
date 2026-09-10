"""Offline contract tests using real .msg field lists and fake ROS/MQTT I/O.

Run from the repository root:
  python3 -m unittest discover -s src/idc_web/idc_bridge/test -v
These tests do not claim DDS discovery or live-broker verification.
"""
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'src/idc_web/idc_bridge'))
from idc_bridge.event_outbox import EventOutbox


class Node:
    namespace = 'robot5'
    queue_path = ''

    def __init__(self, name):
        self.params = {}
        self.subscriptions = []
        self.timers = []
        self.logger = Mock()

    def declare_parameter(self, key, default):
        self.params[key] = {'robot_namespace': self.namespace,
                            'event_queue_path': self.queue_path}.get(key, default)

    def get_parameter(self, key):
        value = self.params[key]
        return NS(value=value, get_parameter_value=lambda: NS(
            string_value=value, integer_value=value))

    def create_subscription(self, msg_type, topic, callback, qos):
        self.subscriptions.append((msg_type, topic, callback, qos))

    def create_timer(self, period, callback):
        self.timers.append((period, callback))

    def get_logger(self):
        return self.logger

    def destroy_node(self):
        return True


class Client:
    def __init__(self, *args, **kwargs):
        self.connected = False
        self.sent = []
        self.next_rc = 0
        self.early_ack = False

    def reconnect_delay_set(self, **kwargs):
        pass

    def connect_async(self, *args, **kwargs):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def publish(self, topic, encoded, qos, retain):
        mid = len(self.sent) + 1
        self.sent.append((topic, json.loads(encoded), qos, retain, mid))
        if self.early_ack:
            self.on_publish(self, None, mid, NS(is_failure=False), None)
        return NS(rc=self.next_rc, mid=mid)


def module(name, **attrs):
    result = ModuleType(name)
    result.__dict__.update(attrs)
    return result


fake_mqtt = module('paho.mqtt.client', Client=Client,
                   CallbackAPIVersion=NS(VERSION2=2),
                   MQTT_ERR_SUCCESS=0, MQTT_ERR_NO_CONN=4)
stubs = {
    'paho': module('paho'), 'paho.mqtt': module('paho.mqtt', client=fake_mqtt),
    'paho.mqtt.client': fake_mqtt, 'rclpy': module('rclpy'),
    'rclpy.node': module('rclpy.node', Node=Node),
    'rclpy.qos': module('rclpy.qos', qos_profile_sensor_data='sensor'),
    'rclpy.time': module('rclpy.time', Time=lambda: None),
    'sensor_msgs': module('sensor_msgs'),
    'sensor_msgs.msg': module('sensor_msgs.msg', BatteryState=NS),
    'tf2_ros': module('tf2_ros', Buffer=Mock, TransformException=LookupError,
                      TransformListener=lambda *args: None),
    'idc_msgs': module('idc_msgs'),
    'idc_msgs.msg': module('idc_msgs.msg', MissionState=NS, SecurityEvent=NS),
}
with patch.dict(sys.modules, stubs):
    bridge_module = importlib.import_module('idc_bridge.mqtt_bridge')


def ros_message(name, **overrides):
    """Fields come from the checked-out interface, not a hand-copied old schema."""
    values = {}
    path = REPO / f'src/idc_msgs/msg/{name}.msg'
    for line in path.read_text().splitlines():
        parts = line.split('#')[0].split()
        if len(parts) != 2:
            continue
        kind, field = parts
        values[field] = {'string': '', 'int32': 0, 'float32': 0.0,
                         'bool': False}.get(kind)
    unknown = overrides.keys() - values.keys()
    if unknown:
        raise AssertionError(f'Unknown ROS fields: {unknown}')
    values.update(overrides)
    return NS(**values)


def event(robot='robot5', **kwargs):
    values = dict(robot_id=robot, type='E5', zone_id='Z1', rack_id='R17',
                  position=NS(x=2.975, y=4.1575, z=0.0), basis='yolo',
                  open_ratio=0.8, frames=15, marker_checked=False,
                  header=NS(stamp=NS(sec=123, nanosec=456), frame_id='map'))
    values.update(kwargs)
    return ros_message('SecurityEvent', **values)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bridge = self.make_bridge('robot5')

    def make_bridge(self, robot):
        Node.namespace = robot
        Node.queue_path = str(Path(self.tmp.name) / f'{robot}.sqlite3')
        result = bridge_module.MqttBridge()
        self.addCleanup(result.destroy_node)
        return result

    def ack(self, bridge, mid):
        bridge._on_mqtt_publish(None, None, mid, NS(is_failure=False), None)
        bridge.publish_pending_event()

    def test_global_subscription_and_startup_without_broker(self):
        self.assertIn('/event/events', [s[1] for s in self.bridge.subscriptions])
        self.bridge.security_event_callback(event())
        self.assertIsNotNone(self.bridge.event_outbox.peek())
        self.assertEqual(self.bridge.mqtt_client.sent, [])

    def test_latest_mission_message_has_no_waypoint_fields(self):
        msg = ros_message('MissionState', robot_id='robot5', state='INSPECT',
                          zone_id='Z1', expected_rack_id='R17', rack_idx=3,
                          rack_total=28, battery=0.7, note='')
        self.bridge.mission_state_callback(msg)
        topic, payload, qos, retain, _ = self.bridge.mqtt_client.sent[0]
        self.assertEqual(topic, 'idc/robot5/mission/state')
        self.assertEqual((qos, retain), (1, False))
        self.assertEqual(payload['rack_idx'], 3)
        self.assertEqual(payload['rack_total'], 28)
        self.assertEqual(payload['expected_rack_id'], 'R17')
        self.assertEqual(payload['zone_id'], 'Z1')
        self.assertFalse(any(k.startswith('waypoint') for k in payload))

    def test_other_robot_mission_is_ignored(self):
        self.bridge.mission_state_callback(ros_message('MissionState', robot_id='robot11'))
        self.assertEqual(self.bridge.mqtt_client.sent, [])

    def test_two_bridges_route_global_events_once_per_robot(self):
        other = self.make_bridge('robot11')
        for bridge in (self.bridge, other):
            bridge.mqtt_client.connected = True
            bridge.security_event_callback(event('robot5'))
            bridge.security_event_callback(event('robot11'))
            self.assertEqual(len(bridge.mqtt_client.sent), 1)
            self.assertEqual(bridge.mqtt_client.sent[0][1]['robot_id'], bridge.robot_id)

    def test_event_fields_and_types_for_both_bases(self):
        for basis in ('yolo', 'marker_missing'):
            with self.subTest(basis=basis):
                self.bridge.mqtt_client.connected = True
                self.bridge.security_event_callback(event(basis=basis, marker_checked=True))
                topic, p, qos, retain, mid = self.bridge.mqtt_client.sent[-1]
                self.assertEqual((topic, qos, retain), ('idc/events/security', 1, False))
                self.assertEqual((p['basis'], p['open_ratio'], p['frames'], p['marker_checked']),
                                 (basis, 0.8, 15, True))
                self.assertEqual(p['stamp'], {'sec': 123, 'nanosec': 456})
                self.assertEqual(p['position'], {'x': 2.975, 'y': 4.1575, 'z': 0.0})
                self.assertEqual(type(p['frames']), int)
                self.assertEqual(type(p['marker_checked']), bool)
                self.assertFalse({'severity', 'evidence_ids', 'detail_json'} & p.keys())
                self.ack(self.bridge, mid)

    def test_puback_required_and_unrelated_ack_does_not_delete(self):
        self.bridge.mqtt_client.connected = True
        self.bridge.security_event_callback(event())
        self.ack(self.bridge, 999)
        self.assertIsNotNone(self.bridge.event_outbox.peek())
        self.assertEqual(len(self.bridge.mqtt_client.sent), 1)
        self.ack(self.bridge, 1)
        self.assertIsNone(self.bridge.event_outbox.peek())

    def test_ack_racing_with_publish_return(self):
        self.bridge.mqtt_client.connected = True
        self.bridge.mqtt_client.early_ack = True
        self.bridge.security_event_callback(event())
        self.bridge.publish_pending_event()
        self.assertIsNone(self.bridge.event_outbox.peek())

    def test_disconnect_race_does_not_enqueue_multiple_paho_messages(self):
        self.bridge.mqtt_client.connected = True
        self.bridge.mqtt_client.next_rc = 4
        self.bridge.security_event_callback(event())
        for _ in range(5):
            self.bridge.publish_pending_event()
        self.assertEqual(len(self.bridge.mqtt_client.sent), 1)
        self.ack(self.bridge, 1)
        self.assertIsNone(self.bridge.event_outbox.peek())

    def test_queue_rejection_leaves_event_for_retry(self):
        self.bridge.mqtt_client.connected = True
        self.bridge.mqtt_client.next_rc = 15
        self.bridge.security_event_callback(event())
        self.assertIsNone(self.bridge.event_inflight)
        self.assertIsNotNone(self.bridge.event_outbox.peek())
        self.bridge.mqtt_client.next_rc = 0
        self.bridge.publish_pending_event()
        self.ack(self.bridge, 2)
        self.assertIsNone(self.bridge.event_outbox.peek())

    def test_disk_queue_survives_restart_preserves_time_and_fifo(self):
        self.bridge.security_event_callback(event())
        self.bridge.security_event_callback(event(rack_id='R18'))
        expected = self.bridge.event_outbox.peek()[1]
        self.bridge.event_outbox.close()
        self.bridge.event_outbox = EventOutbox(Path(self.tmp.name) / 'robot5.sqlite3')
        self.bridge.mqtt_client.connected = True
        self.bridge.publish_pending_event()
        self.assertEqual(self.bridge.mqtt_client.sent[0][1], json.loads(expected))
        self.ack(self.bridge, 1)
        self.assertEqual(self.bridge.mqtt_client.sent[1][1]['rack_id'], 'R18')

    def test_nonfinite_values_are_json_null(self):
        self.bridge.mqtt_client.connected = True
        self.bridge.security_event_callback(event(open_ratio=float('nan'),
            position=NS(x=float('inf'), y=1.0, z=0.0)))
        payload = self.bridge.mqtt_client.sent[0][1]
        self.assertIsNone(payload['open_ratio'])
        self.assertIsNone(payload['position']['x'])

    def test_battery_payload_regression(self):
        self.bridge.battery_callback(NS(percentage=0.74, voltage=24.0,
            temperature=25.0, present=True, header=NS(stamp=NS(sec=1, nanosec=2))))
        self.bridge.publish_battery()
        topic, payload, qos, retain, _ = self.bridge.mqtt_client.sent[0]
        self.assertEqual((topic, qos, retain), ('idc/robot5/battery', 1, False))
        self.assertEqual(payload['battery_percent'], 74.0)

    def test_pose_payload_regression(self):
        self.bridge.tf_buffer.lookup_transform.return_value = NS(
            transform=NS(translation=NS(x=1., y=2.), rotation=NS(x=0., y=0., z=0., w=1.)),
            header=NS(stamp=NS(sec=1, nanosec=2)))
        self.bridge.publish_pose()
        topic, payload, qos, retain, _ = self.bridge.mqtt_client.sent[0]
        self.assertEqual((topic, qos, retain), ('idc/robot5/pose', 0, False))
        self.assertEqual((payload['x'], payload['y'], payload['yaw']), (1., 2., 0.))


if __name__ == '__main__':
    unittest.main()
