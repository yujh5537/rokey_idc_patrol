#!/usr/bin/env python3
"""
check_map_alignment.py — 로봇 TF 위치와 병합 지도(/map)의 world 정렬을 한 번에 비교

아래 4가지를 동시에 뽑아서 표로 보여준다.
  1) map_merge_params.yaml 의 init_pose_* 값 (파일에서 직접 읽음)
  2) 실제 발행 중인 static TF world->robotN/map (tf_static)
  3) 로봇 N 의 실제 위치 world->robotN/base_link (정상 확인 기준)
  4) 병합 지도 /map 의 header.frame_id 와 info.origin / info.width·height

목적: "init_pose 와 static TF 가 같은가?" 뿐 아니라
     "그 값이 실제로 /map 의 origin 에 반영됐는가?" 까지 눈으로 확인.

사용법:
  # ROS 환경 source 후
  python3 amr/scripts/check_map_alignment.py
  python3 amr/scripts/check_map_alignment.py --params amr/config/map_merge_params.yaml \
      --robots robot5 robot11 --map-topic /map --world world
"""

import argparse
import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, HistoryPolicy

import yaml
from nav_msgs.msg import OccupancyGrid
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformListener


def quat_to_yaw(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def read_params(path, robots):
    """map_merge_params.yaml 에서 /<robot>/map_merge/init_pose_* 를 뽑는다."""
    with open(path) as f:
        doc = yaml.safe_load(f)
    # RewrittenYaml 이전의 원본 파일 값. 실행 시엔 launch 인자로 덮어써질 수 있음.
    ros__params = doc.get('map_merge', {}).get('ros__parameters', {})
    out = {}
    for r in robots:
        pref = f'/{r}/map_merge/init_pose_'
        out[r] = {
            'x': ros__params.get(pref + 'x'),
            'y': ros__params.get(pref + 'y'),
            'yaw': ros__params.get(pref + 'yaw'),
        }
    return out


class Checker(Node):
    def __init__(self, robots, map_topic, world):
        super().__init__('check_map_alignment')
        self.robots = robots
        self.world = world
        self.map_msg = None

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # /map 은 latched (transient_local)
        qos = QoSProfile(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, map_topic, self._on_map, qos)

    def _on_map(self, msg):
        self.map_msg = msg

    def lookup(self, target):
        try:
            t = self.tf_buffer.lookup_transform(
                self.world, target, rclpy.time.Time())
            tr = t.transform.translation
            return (tr.x, tr.y, quat_to_yaw(t.transform.rotation))
        except Exception as e:  # noqa: BLE001
            return f'조회 실패: {e}'


def fmt(v):
    if isinstance(v, (int, float)):
        return f'{v:+.3f}'
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--params', default='amr/config/map_merge_params.yaml')
    ap.add_argument('--robots', nargs='+', default=['robot5', 'robot11'])
    ap.add_argument('--map-topic', default='/map')
    ap.add_argument('--world', default='world')
    ap.add_argument('--settle', type=float, default=3.0,
                    help='TF/맵 수집 대기 시간(초)')
    args, ros_args = ap.parse_known_args()

    try:
        params = read_params(args.params, args.robots)
    except FileNotFoundError:
        print(f'[경고] 파라미터 파일 없음: {args.params}')
        params = {r: {'x': None, 'y': None, 'yaw': None} for r in args.robots}

    rclpy.init(args=ros_args)
    node = Checker(args.robots, args.map_topic, args.world)

    end = node.get_clock().now().nanoseconds + int(args.settle * 1e9)
    while rclpy.ok() and node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.1)

    print()
    print('=' * 72)
    print(f'{"":16} | {"init_pose(yaml)":>22} | {"static TF world->map":>22}')
    print(f'{"":16} | {"x       y      yaw":>22} | {"x       y      yaw":>22}')
    print('-' * 72)
    for r in args.robots:
        p = params[r]
        p_str = f'{fmt(p["x"]):>7} {fmt(p["y"]):>6} {fmt(p["yaw"]):>6}'
        tf_map = node.lookup(f'{r}/map')
        if isinstance(tf_map, tuple):
            tf_str = f'{tf_map[0]:+7.3f} {tf_map[1]:+6.3f} {tf_map[2]:+6.3f}'
        else:
            tf_str = tf_map
        print(f'{r:16} | {p_str:>22} | {tf_str:>22}')

    print()
    print('로봇 실제 위치 (world -> <ns>/base_link) — 정상 확인 기준:')
    for r in args.robots:
        bl = node.lookup(f'{r}/base_link')
        if isinstance(bl, tuple):
            print(f'  {r:10} x={bl[0]:+.3f}  y={bl[1]:+.3f}  yaw={bl[2]:+.3f}')
        else:
            print(f'  {r:10} {bl}')

    print()
    print(f'병합 지도 ({args.map_topic}):')
    m = node.map_msg
    if m is None:
        print('  수신 실패 — map_merge 가 발행 중인지, 토픽 이름이 맞는지 확인')
    else:
        o = m.info.origin
        w_m = m.info.width * m.info.resolution
        h_m = m.info.height * m.info.resolution
        print(f'  header.frame_id : {m.header.frame_id}')
        print(f'  resolution      : {m.info.resolution:.4f} m/px')
        print(f'  size            : {m.info.width} x {m.info.height} px '
              f'({w_m:.2f} x {h_m:.2f} m)')
        print(f'  info.origin     : x={o.position.x:+.3f}  y={o.position.y:+.3f}  '
              f'yaw={quat_to_yaw(o.orientation):+.3f}')
        print(f'  => 지도 중심의 world 좌표 : '
              f'x={o.position.x + w_m / 2:+.3f}  y={o.position.y + h_m / 2:+.3f}')
        print()
        print('  [해석] m-explore-ros2 map_merge 는 known_init_poses 모드에서')
        print('         info.origin 을 항상 (-width/2, -height/2, yaw=0) 으로 강제한다.')
        print('         즉 위 init_pose / static TF 값은 /map 의 world 배치에 반영되지 않는다.')
        print('         지도 중심 world 좌표가 (0,0) 근처면 이 강제 동작이 맞다는 신호.')

    print('=' * 72)

    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
