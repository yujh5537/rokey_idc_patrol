"""Event_engine — PC3. server.launch.py 에 include (INF-07, R1). 영상 미구독."""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(package="idc_event", executable="event_engine", name="event_engine",
             parameters=[{"robots": ["robot5", "robot11"], "objects_timeout_sec": 5.0}],
             respawn=True, respawn_delay=2.0, output="screen"),
    ])
