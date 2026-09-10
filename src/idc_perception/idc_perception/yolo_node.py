#!/usr/bin/env python3
"""
yolo_node — raw 이미지 → 도어 박스(Detection2DArray) + 주석 이미지 (SDD 5.4, PER-01)
배치: PC1(/robot5) · PC2(/robot11). 실행 시 --ros-args -r __ns:=/robotN 로 네임스페이스 지정.
모델: idc_door_v1.pt (클래스 0 rack_door_open / 1 rack_door_closed, conf 0.5, imgsz 640)
"""
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CompressedImage
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose
from cv_bridge import CvBridge
from ultralytics import YOLO

DOOR_CLASSES = ("rack_door_open", "rack_door_closed")   # DAT-01 순서 고정


class YoloNode(Node):
    def __init__(self):
        super().__init__("yolo_node")
        # --- 파라미터 (launch/config로 덮어씀. 절대 경로 하드코딩 금지) ---
        self.declare_parameter("model_path", "")          # 필수: idc_door_v1.pt 경로
        self.declare_parameter("conf", 0.5)
        self.declare_parameter("imgsz", 640)
        self.declare_parameter("device", "cpu")           # PC1·PC2 GPU 있으면 "0"
        self.declare_parameter("max_fps", 10.0)           # 추론 상한 (CPU 보호)
        self.declare_parameter("publish_annotated", True)
        self.declare_parameter("annotated_hz", 5.0)       # SDD 4.2.1 image_annotated 5Hz

        def p(n):
            return self.get_parameter(n).value

        model_path = p("model_path")
        if not model_path:
            raise RuntimeError("model_path 파라미터가 비어 있음 (-p model_path:=/path/idc_door_v1.pt)")
        self.conf, self.imgsz, self.device = float(p("conf")), int(p("imgsz")), p("device")
        self.min_dt = 1.0 / float(p("max_fps"))
        self.pub_ann, self.ann_dt = bool(p("publish_annotated")), 1.0 / float(p("annotated_hz"))

        self.model = YOLO(model_path)
        self.names = self.model.names                      # {0:'rack_door_open', 1:'rack_door_closed'}
        if tuple(self.names.get(i) for i in (0, 1)) != DOOR_CLASSES:
            self.get_logger().warn(
                f"모델 클래스가 DAT-01과 다름: {self.names} — 도어 판정 불가(파이프라인 확인용)")
        # 첫 추론 지연 제거(워밍업)
        self.model.predict(np.zeros((self.imgsz, self.imgsz, 3), np.uint8),
                           imgsz=self.imgsz, device=self.device, verbose=False)

        self.bridge = CvBridge()
        self.last_infer_t = 0.0
        self.last_ann_t = 0.0
        self.fps_win = []

        # 상대 토픽명 → 네임스페이스로 /robotN/... 이 됨
        self.sub = self.create_subscription(Image, "oakd/rgb/image_raw", self.on_image, qos_profile_sensor_data)
        self.pub_det = self.create_publisher(Detection2DArray, "perception/detections", 10)
        self.pub_img = self.create_publisher(CompressedImage, "perception/image_annotated", qos_profile_sensor_data)
        self.get_logger().info(
            f"yolo_node up: model={model_path} conf={self.conf} imgsz={self.imgsz} device={self.device}")

    def on_image(self, msg: Image):
        now = time.monotonic()
        if now - self.last_infer_t < self.min_dt:          # 프레임 스킵으로 CPU 상한
            return
        self.last_infer_t = now
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        res = self.model.predict(frame, conf=self.conf, imgsz=self.imgsz, device=self.device, verbose=False)[0]

        out = Detection2DArray()
        out.header = msg.header                             # 이미지 stamp 그대로 → perception_node에서 동기화
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            d = Detection2D()
            d.header = msg.header
            d.bbox.center.position.x = (x1 + x2) / 2.0
            d.bbox.center.position.y = (y1 + y2) / 2.0
            d.bbox.size_x, d.bbox.size_y = (x2 - x1), (y2 - y1)
            h = ObjectHypothesisWithPose()
            h.hypothesis.class_id = str(self.names[int(b.cls[0])])   # "rack_door_open" | "rack_door_closed"
            h.hypothesis.score = float(b.conf[0])
            d.results.append(h)
            out.detections.append(d)
        self.pub_det.publish(out)

        # FPS 로그 (PER-06 완료기준 ≥5FPS 기록용)
        self.fps_win.append(now)
        self.fps_win = [t for t in self.fps_win if now - t < 2.0]
        if len(self.fps_win) >= 2:
            self.get_logger().info(
                f"YOLO FPS≈{len(self.fps_win) / 2.0:.1f}  boxes={len(out.detections)}",
                throttle_duration_sec=5.0)

        if self.pub_ann and now - self.last_ann_t >= self.ann_dt:
            self.last_ann_t = now
            ann = res.plot()
            # 화면 중앙선 — perception_node의 "중앙 랙" 판정 기준선 시각화
            cv2.line(ann, (ann.shape[1] // 2, 0), (ann.shape[1] // 2, ann.shape[0]), (0, 255, 255), 1)
            ok, buf = cv2.imencode(".jpg", ann, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                cm = CompressedImage(header=msg.header, format="jpeg", data=buf.tobytes())
                self.pub_img.publish(cm)


def main():
    rclpy.init()
    node = YoloNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
