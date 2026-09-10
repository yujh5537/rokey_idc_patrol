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
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg = get_package_share_directory("idc_perception")
    params = os.path.join(pkg, "config", "perception_params.yaml")
    ns = LaunchConfiguration("namespace")
    model = LaunchConfiguration("model_path")
    device = LaunchConfiguration("device")
    # launch 인자는 문자열이다. int 로 선언한 파라미터에 그대로 넘기면
    # InvalidParameterTypeException 으로 노드가 기동 실패한다 — 명시 캐스팅.
    imgsz = ParameterValue(LaunchConfiguration("imgsz"), value_type=int)
    image_width = ParameterValue(LaunchConfiguration("image_width"), value_type=int)
    use_republish = LaunchConfiguration("use_republish")

    return LaunchDescription([
        DeclareLaunchArgument("namespace", description="robot5 | robot11"),
        DeclareLaunchArgument("model_path", description="YOLO .pt 절대 경로 (레포 밖)"),
        DeclareLaunchArgument("device", default_value="0",
                              description="CUDA 디바이스 인덱스. GPU 없으면 cpu"),
        DeclareLaunchArgument("imgsz", default_value="640"),
        DeclareLaunchArgument("image_width", default_value="704",
                              description="camera_info 수신 전 폴백 폭. 실측 OAK-D=704"),
        DeclareLaunchArgument("use_republish", default_value="true",
                              description="compressed→raw 변환 노드 포함 여부 (INF-04 republish가 이미 돌면 false)"),

        # compressed → raw (SDD 5.4 republish). 상대 토픽 → /robotN/oakd/rgb/image_raw
        # ※ republish 는 구독 QoS 가 기본 RELIABLE 인데 카메라는 SensorData(BEST_EFFORT) 로 발행한다.
        #    맞추지 않으면 "incompatible QoS. No messages will be sent" 경고 한 줄만 남기고
        #    raw 가 한 프레임도 안 나온다(= objects 0). QoS 오버라이드 키에 FQN 토픽이 들어가므로
        #    네임스페이스를 치환으로 끼워 넣는다.
        Node(package="image_transport", executable="republish", name="republish", namespace=ns,
             parameters=[{
                 "in_transport": "compressed",
                 "out_transport": "raw",
                 ("qos_overrides./", ns, "/oakd/rgb/image_raw/compressed.subscription.reliability"):
                     "best_effort",
             }],
             remappings=[("in/compressed", "oakd/rgb/image_raw/compressed"),
                         ("out", "oakd/rgb/image_raw")],
             condition=IfCondition(use_republish), output="screen"),

        Node(package="idc_perception", executable="yolo_node", name="yolo_node", namespace=ns,
             parameters=[params, {"model_path": model, "device": device, "imgsz": imgsz}],
             respawn=True, respawn_delay=2.0, output="screen"),        # SDD 7장 respawn

        Node(package="idc_perception", executable="aruco_node", name="aruco_node", namespace=ns,
             parameters=[params], respawn=True, respawn_delay=2.0, output="screen"),

        Node(package="idc_perception", executable="perception_node", name="perception_node", namespace=ns,
             parameters=[params, {"image_width": image_width}],
             respawn=True, respawn_delay=2.0, output="screen"),
    ])
