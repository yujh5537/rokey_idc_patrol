"""idc_perception 4노드 launch — PC1(robot5) / PC2(robot11). SDD 5.4·9장.
단독:  ros2 launch idc_perception perception.launch.py namespace:=robot5 model_path:=$HOME/idc_ws/models/idc_door_v1.pt
편입:  patrol_robot.launch.py 에서 IncludeLaunchDescription 으로 포함 (INF-07, R1)"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("idc_perception")
    params = os.path.join(pkg, "config", "perception_params.yaml")
    ns = LaunchConfiguration("namespace")
    model = LaunchConfiguration("model_path")
    device = LaunchConfiguration("device")
    imgsz = LaunchConfiguration("imgsz")
    use_republish = LaunchConfiguration("use_republish")

    return LaunchDescription([
        DeclareLaunchArgument("namespace", description="robot5 | robot11"),
        DeclareLaunchArgument("model_path", description="YOLO .pt 절대 경로 (레포 밖)"),
        DeclareLaunchArgument("device", default_value="cpu"),
        DeclareLaunchArgument("imgsz", default_value="640"),
        DeclareLaunchArgument("use_republish", default_value="true",
                              description="compressed→raw 변환 노드 포함 여부 (INF-04 republish가 이미 돌면 false)"),

        # compressed → raw (SDD 5.4 republish). 상대 토픽 → /robotN/oakd/rgb/image_raw
        Node(package="image_transport", executable="republish", name="republish", namespace=ns,
             parameters=[{"in_transport": "compressed", "out_transport": "raw"}],
             remappings=[("in/compressed", "oakd/rgb/image_raw/compressed"),
                         ("out", "oakd/rgb/image_raw")],
             condition=IfCondition(use_republish), output="screen"),

        Node(package="idc_perception", executable="yolo_node", name="yolo_node", namespace=ns,
             parameters=[params, {"model_path": model, "device": device, "imgsz": imgsz}],
             respawn=True, respawn_delay=2.0, output="screen"),        # SDD 7장 respawn

        Node(package="idc_perception", executable="aruco_node", name="aruco_node", namespace=ns,
             parameters=[params], respawn=True, respawn_delay=2.0, output="screen"),

        Node(package="idc_perception", executable="perception_node", name="perception_node", namespace=ns,
             parameters=[params], respawn=True, respawn_delay=2.0, output="screen"),
    ])
