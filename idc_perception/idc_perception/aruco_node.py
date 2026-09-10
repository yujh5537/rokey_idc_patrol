#!/usr/bin/env python3
"""
aruco_node — raw 이미지 → 마커 [{aruco_id, 중심}] (Detection2DArray) (SDD 5.4, PER-02)
배치: PC1·PC2. DICT_5X5_250, marker_len 0.02m. camera_info는 선택(중심 검출엔 불필요, 로그용).
class_id = str(aruco_id) — perception_node가 int()로 되돌려 "R%02d" 로 변환.
"""
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose
from cv_bridge import CvBridge


class ArucoNode(Node):
    def __init__(self):
        super().__init__("aruco_node")
        self.declare_parameter("dictionary", "DICT_5X5_250")   # SDD 3.1 (A1·A2b 확인 시 변경)
        self.declare_parameter("marker_len", 0.02)              # m — 포즈 추정은 안 하므로 기록용
        self.declare_parameter("min_id", 1)
        self.declare_parameter("max_id", 56)                    # racks.yaml aruco_id 1~56 밖은 버림
        self.declare_parameter("log_hz", 1.0)

        dname = self.get_parameter("dictionary").value
        if not hasattr(cv2.aruco, dname):
            raise RuntimeError(f"cv2.aruco에 {dname} 없음")
        self.min_id = int(self.get_parameter("min_id").value)
        self.max_id = int(self.get_parameter("max_id").value)
        self.log_dt = 1.0 / float(self.get_parameter("log_hz").value)

        # OpenCV >=4.7 신 API
        self.dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dname))
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX   # 20mm 소형 마커 안정화
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, params)

        self.bridge = CvBridge()
        self.cam_info = None
        self._last_log = 0.0

        self.sub = self.create_subscription(Image, "oakd/rgb/image_raw", self.on_image, qos_profile_sensor_data)
        self.sub_ci = self.create_subscription(CameraInfo, "oakd/rgb/camera_info", self.on_info, qos_profile_sensor_data)
        self.pub = self.create_publisher(Detection2DArray, "perception/markers", 10)
        self.get_logger().info(f"aruco_node up: {dname}, id {self.min_id}..{self.max_id}")

    def on_info(self, msg: CameraInfo):
        if self.cam_info is None:
            self.get_logger().info(f"camera_info 수신 {msg.width}x{msg.height}")
        self.cam_info = msg

    def on_image(self, msg: Image):
        gray = self.bridge.imgmsg_to_cv2(msg, desired_encoding="mono8")
        corners, ids, _ = self.detector.detectMarkers(gray)

        out = Detection2DArray()
        out.header = msg.header
        if ids is not None:
            for c, i in zip(corners, ids.flatten()):
                i = int(i)
                if not (self.min_id <= i <= self.max_id):
                    continue
                pts = c[0]                                 # 4x2
                d = Detection2D()
                d.header = msg.header
                d.bbox.center.position.x = float(pts[:, 0].mean())
                d.bbox.center.position.y = float(pts[:, 1].mean())
                d.bbox.size_x = float(pts[:, 0].max() - pts[:, 0].min())
                d.bbox.size_y = float(pts[:, 1].max() - pts[:, 1].min())
                h = ObjectHypothesisWithPose()
                h.hypothesis.class_id = str(i)
                h.hypothesis.score = 1.0
                d.results.append(h)
                out.detections.append(d)
        self.pub.publish(out)

        t = self.get_clock().now().nanoseconds * 1e-9
        if t - self._last_log >= self.log_dt:
            self._last_log = t
            found = [int(d.results[0].hypothesis.class_id) for d in out.detections]
            self.get_logger().info(f"markers={found}")


def main():
    rclpy.init()
    node = ArucoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
