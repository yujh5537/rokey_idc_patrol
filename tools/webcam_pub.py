#!/usr/bin/env python3
"""webcam_pub — v4l2_camera 없이 웹캠을 로봇 카메라 토픽명으로 위장 발행 (STEP 2 대리 검증용).
apt 설치 권한이 없을 때의 대체 경로. 실기에서는 쓰지 않는다.
사용: ros2 run 은 불가(패키지 밖). python3 tools/webcam_pub.py --ros-args -r __ns:=/robot5
"""
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge


class WebcamPub(Node):
    def __init__(self):
        super().__init__("webcam_pub")
        self.declare_parameter("device", 0)
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 15.0)
        self.declare_parameter("frame_id", "oakd_rgb_camera_optical_frame")

        dev = int(self.get_parameter("device").value)
        w = int(self.get_parameter("width").value)
        h = int(self.get_parameter("height").value)
        fps = float(self.get_parameter("fps").value)
        self.frame_id = self.get_parameter("frame_id").value

        self.cap = cv2.VideoCapture(dev)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if not self.cap.isOpened():
            raise RuntimeError(f"/dev/video{dev} 열기 실패")

        self.bridge = CvBridge()
        self.pub = self.create_publisher(Image, "oakd/rgb/image_raw", qos_profile_sensor_data)
        self.pub_ci = self.create_publisher(CameraInfo, "oakd/rgb/camera_info", qos_profile_sensor_data)
        self.w, self.h = w, h
        self.timer = self.create_timer(1.0 / fps, self.tick)
        self.get_logger().info(f"webcam_pub up: /dev/video{dev} {w}x{h}@{fps}Hz ns={self.get_namespace()}")

    def tick(self):
        ok, frame = self.cap.read()
        if not ok:
            self.get_logger().warn("프레임 읽기 실패", throttle_duration_sec=5.0)
            return
        msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        self.pub.publish(msg)
        # 캘리브레이션 없는 더미 — aruco_node는 중심 검출만 하므로 K가 없어도 동작
        ci = CameraInfo(header=msg.header, width=self.w, height=self.h)
        self.pub_ci.publish(ci)

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()


def main():
    rclpy.init()
    node = WebcamPub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
