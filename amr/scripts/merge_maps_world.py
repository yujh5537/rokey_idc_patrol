#!/usr/bin/env python3
"""
merge_maps_world.py — world 좌표계에 정확히 정렬되는 멀티로봇 지도 병합

multirobot_map_merge(m-explore-ros2) 를 대체한다. 그 패키지는 known_init_poses
모드에서
  - init_pose 이동값을 미터가 아니라 픽셀로 적용하고
  - 회전을 그리드 프레임 원점이 아니라 픽셀 (0,0) 모서리 기준으로 돌리고
  - 출력 /map 의 info.origin 을 항상 (-width/2, -height/2, yaw=0) 으로 강제
하므로, 로봇 TF 는 정상인데 /map 만 world 기준으로 어긋난다.

이 노드는 도크 배치가 고정·기지값이라는 점을 이용해 직접 래스터화한다.

  1. /<ns>/map 을 각각 구독
  2. 각 입력 셀의 world 좌표 =  T(world<-<ns>/map)  ∘  grid.info.origin  ∘  (cell·res)
     - T(world<-<ns>/map) 는 control_pc_full.launch.py 의 r5_*/r11_* (= static TF
       world->robotN/map 인자) 와 동일한 값. --pose 로 받는다.
  3. 두 입력 그리드의 world AABB 합집합을 덮는, world 축에 정렬된(회전 0) 출력
     그리드를 잡는다
  4. 출력 셀마다 각 입력 그리드로 역매핑해 표본을 얻고 max 합성
     (occupied 100 > free 0 > unknown -1)
  5. info.origin 에 실제 world 좌표(xmin, ymin), orientation identity, frame_id
     world 로 발행 (latched)

사용법:
  python3 merge_maps_world.py \
    --pose robot5  0.0 0.0 3.14159265 \
    --pose robot11 0.0 4.53 3.14159265 \
    --map-topic map --merged-topic /map --world-frame world --rate 2.0

  control_pc_full.launch.py 가 merge_script:= 인자로 이 스크립트를 실행하고
  --pose 값을 r5_*/r11_* 에서 만들어 넘긴다 (좌표 단일 소스 유지).
"""

import argparse
import math

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy)
from nav_msgs.msg import OccupancyGrid

MAX_OUT_CELLS = 8_000_000  # 출력 그리드 상한 (약 8M 셀 = 0.05m 기준 141m x 141m)


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def rot(theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


class WorldMapMerger(Node):
    def __init__(self, poses, map_topic, merged_topic, world_frame,
                 rate, out_res):
        super().__init__('merge_maps_world')
        self.poses = poses                # {ns: (x, y, yaw)}
        self.world_frame = world_frame
        self.out_res = out_res            # <=0 이면 첫 입력 그리드 resolution 사용
        self.grids = {}                   # ns -> 최신 OccupancyGrid

        sub_qos = QoSProfile(
            depth=5, history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)  # slam_toolbox /map 은 latched
        for ns, pose in poses.items():
            topic = map_topic if map_topic.startswith('/') else f'/{ns}/{map_topic}'
            self.create_subscription(
                OccupancyGrid, topic,
                lambda msg, n=ns: self._on_map(n, msg), sub_qos)
            self.get_logger().info(
                f'구독 {topic}   world<-{ns}/map = '
                f'(x={pose[0]:+.3f}, y={pose[1]:+.3f}, yaw={pose[2]:+.3f})')

        pub_qos = QoSProfile(
            depth=1, history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.pub = self.create_publisher(OccupancyGrid, merged_topic, pub_qos)
        self.timer = self.create_timer(1.0 / max(rate, 0.1), self._tick)
        self.get_logger().info(
            f'발행 {merged_topic}  (frame_id={world_frame}, {rate:.1f} Hz)')

    def _on_map(self, ns, msg):
        self.grids[ns] = msg

    def _grid_affine(self, ns, info):
        """그리드 인덱스 (i, j) -> world 미터.  world = A @ [i, j] + b (2x2 affine)."""
        tx, ty, yaw_n = self.poses[ns]
        g_yaw = yaw_of(info.origin.orientation)          # 보통 0
        res = info.resolution
        A = rot(yaw_n + g_yaw) * res
        o = np.array([info.origin.position.x, info.origin.position.y])
        b = rot(yaw_n) @ o + np.array([tx, ty])
        return A, b

    def _tick(self):
        grids = dict(self.grids)
        if not grids:
            return

        res = self.out_res
        if res <= 0.0:
            res = float(next(iter(grids.values())).info.resolution)

        # 1) 모든 입력 그리드의 네 모서리 -> world AABB 합집합
        affines, world_corners = {}, []
        for ns, g in grids.items():
            A, b = self._grid_affine(ns, g.info)
            affines[ns] = (A, b)
            w, h = g.info.width, g.info.height
            corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=np.float64)
            world_corners.append((A @ corners.T).T + b)
        allpts = np.vstack(world_corners)
        xmin, ymin = allpts.min(axis=0)
        xmax, ymax = allpts.max(axis=0)

        out_w = int(math.ceil((xmax - xmin) / res))
        out_h = int(math.ceil((ymax - ymin) / res))
        if out_w <= 0 or out_h <= 0:
            return
        if out_w * out_h > MAX_OUT_CELLS:
            self.get_logger().warn(
                f'출력 그리드 {out_w}x{out_h} (>{MAX_OUT_CELLS} 셀) — 이번 주기 스킵')
            return

        # 2) 출력 셀 중심의 world 좌표
        wx = xmin + (np.arange(out_w) + 0.5) * res
        wy = ymin + (np.arange(out_h) + 0.5) * res
        gx, gy = np.meshgrid(wx, wy)                       # (out_h, out_w)
        world_flat = np.stack([gx.ravel(), gy.ravel()], axis=0)   # (2, N)

        out = np.full(out_h * out_w, -1, dtype=np.int8)

        # 3) 입력별 역매핑 + max 합성
        for ns, g in grids.items():
            A, b = affines[ns]
            idx = np.linalg.inv(A) @ (world_flat - b[:, None])     # (2, N) float (i, j)
            ii = np.floor(idx[0]).astype(np.int64)
            jj = np.floor(idx[1]).astype(np.int64)
            w, h = g.info.width, g.info.height
            m = (ii >= 0) & (ii < w) & (jj >= 0) & (jj < h)
            data = np.asarray(g.data, dtype=np.int8).reshape(h, w)
            sample = np.full(out_h * out_w, -1, dtype=np.int8)
            sample[m] = data[jj[m], ii[m]]
            np.maximum(out, sample, out=out)               # 100 > 0 > -1

        # 4) 발행
        msg = OccupancyGrid()
        now = self.get_clock().now().to_msg()
        msg.header.stamp = now
        msg.header.frame_id = self.world_frame
        msg.info.map_load_time = now
        msg.info.resolution = float(res)
        msg.info.width = out_w
        msg.info.height = out_h
        msg.info.origin.position.x = float(xmin)
        msg.info.origin.position.y = float(ymin)
        msg.info.origin.position.z = 0.0
        msg.info.origin.orientation.w = 1.0
        msg.data = out.tolist()
        self.pub.publish(msg)


def _parse_poses(pose_args):
    if not pose_args:
        raise SystemExit(
            'error: --pose 를 최소 1개 지정하세요. 예: '
            '--pose robot5 0.0 0.0 3.14159265 --pose robot11 0.0 4.53 3.14159265')
    poses = {}
    for ns, x, y, yaw in pose_args:
        poses[ns] = (float(x), float(y), float(yaw))
    return poses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pose', action='append', nargs=4,
                    metavar=('NS', 'X', 'Y', 'YAW'),
                    help='로봇 네임스페이스와 world<-<ns>/map 의 x y yaw. 반복 지정.')
    ap.add_argument('--map-topic', default='map',
                    help="입력 지도 토픽. '/' 없으면 /<ns>/<topic>. 기본 map")
    ap.add_argument('--merged-topic', default='/map', help='출력 토픽. 기본 /map')
    ap.add_argument('--world-frame', default='world', help='출력 frame_id. 기본 world')
    ap.add_argument('--rate', type=float, default=2.0, help='발행 주기 Hz. 기본 2.0')
    ap.add_argument('--resolution', type=float, default=0.0,
                    help='출력 해상도 m/px. 0 이면 첫 입력 그리드 값 사용')
    args, ros_args = ap.parse_known_args()
    poses = _parse_poses(args.pose)

    rclpy.init(args=ros_args)
    node = WorldMapMerger(poses, args.map_topic, args.merged_topic,
                          args.world_frame, args.rate, args.resolution)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
