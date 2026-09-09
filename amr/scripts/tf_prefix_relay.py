#!/usr/bin/env python3
import sys
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from tf2_msgs.msg import TFMessage

ns = sys.argv[sys.argv.index('--ns') + 1]


def add_prefix(msg):
    for t in msg.transforms:
        t.header.frame_id = ns + '/' + t.header.frame_id if not t.header.frame_id.startswith(ns + '/') else t.header.frame_id
        t.child_frame_id = ns + '/' + t.child_frame_id if not t.child_frame_id.startswith(ns + '/') else t.child_frame_id
    return msg


rclpy.init()
node = Node('tf_prefix_relay_' + ns)

pub_tf = node.create_publisher(TFMessage, '/tf', 100)
pub_static = node.create_publisher(TFMessage, '/tf_static', QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL))

node.create_subscription(TFMessage, f'/{ns}/tf', lambda m: pub_tf.publish(add_prefix(m)), 100)
node.create_subscription(TFMessage, f'/{ns}/tf_static', lambda m: pub_static.publish(add_prefix(m)), QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL))

rclpy.spin(node)
