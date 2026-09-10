#!/usr/bin/env python3
"""Robot5 Z4/Z3 patrol on MAP-02 and return docking. Default: preview only."""

import argparse
import math
import signal
import time
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[2] / 'src/idc_bringup/config/racks.yaml'

EXPECTED_ROBOT5_ROUTE = [
    'R56', 'R55', 'R54', 'R53', 'R52', 'R51', 'R50',
    'R43', 'R44', 'R45', 'R46', 'R47', 'R48', 'R49',
    'R42', 'R41', 'R40', 'R39', 'R38', 'R37', 'R36',
    'R29', 'R30', 'R31', 'R32', 'R33', 'R34', 'R35',
]

EXPECTED_MAP = {
    'frame_id': 'map',
    'resolution': 0.05,
    'width': 90,
    'height': 132,
    'origin_x': -0.5,
    'origin_y': -0.5,
}


def map_matches(msg):
    """Reject execution if /robot5/map is not the MAP-02 used by racks.yaml."""
    info = msg.info
    return (
        msg.header.frame_id == EXPECTED_MAP['frame_id']
        and abs(float(info.resolution) - EXPECTED_MAP['resolution']) <= 1e-6
        and int(info.width) == EXPECTED_MAP['width']
        and int(info.height) == EXPECTED_MAP['height']
        and abs(float(info.origin.position.x) - EXPECTED_MAP['origin_x']) <= 1e-3
        and abs(float(info.origin.position.y) - EXPECTED_MAP['origin_y']) <= 1e-3
    )


def build_route(config):
    """Build robot5 patrol in the required Z4 -> Z3 order."""
    racks = {r['rack_id']: r for r in config['racks']}
    ids = list(config['patrol_routes']['robot5'])

    if config['robot_zones']['robot5'] != ['Z3', 'Z4']:
        raise ValueError("racks.yaml must assign robot5 to ['Z3', 'Z4']")
    if ids != EXPECTED_ROBOT5_ROUTE:
        raise ValueError('robot5 patrol route does not match the approved Z4/Z3 order')

    def pose(name, data):
        values = tuple(float(data[k]) for k in ('x', 'y', 'yaw'))
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f'Invalid pose: {name}')
        return (name, *values)

    # robot5 is docked below the middle wall. Move up the left corridor to
    # the wall opening, cross to the rack side, then patrol Z4 first and Z3.
    route = [
        ('dock_midpoint', 0.270, 0.700, math.pi / 2),
        ('z4_midpoint', 1.400, 0.700, 0.0),
    ]

    for zone in ('Z4', 'Z3'):
        entry = config['zones'][zone]['entry_pose']
        route.append(pose(zone + '_entry', entry))

        zone_ids = [rid for rid in ids if racks[rid]['zone_id'] == zone]
        if len(zone_ids) != 14:
            raise ValueError(f'Expected 14 racks in {zone}')

        route.extend(pose(rid, racks[rid]['inspect_pose']) for rid in zone_ids)
        route.append(pose(zone + '_exit', dict(entry, yaw=math.pi)))

    # Return through the center opening to the lower robot5 dock.
    route.extend([
        ('return_z4_midpoint', 1.400, 0.700, math.pi),
        ('return_dock_midpoint', 0.270, 0.700, -math.pi / 2),
    ])
    return route


def run_patrol(navigate, inspect, dock, route):
    """Continue only after Nav2 succeeds; no extra rack TF tolerance check."""
    for waypoint in route:
        if not navigate(waypoint):
            return False
        if waypoint[0].startswith('R') and not inspect(waypoint[0]):
            return False
    return dock()


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='send physical motion goals')
    parser.add_argument('--goal-timeout', type=positive, default=180.0)
    parser.add_argument('--dwell', type=positive, default=3.0)
    parser.add_argument('--dock-timeout', type=positive, default=120.0)
    args = parser.parse_args()

    import yaml

    with CONFIG.open() as stream:
        config = yaml.safe_load(stream)

    route = build_route(config)
    for name, x, y, yaw in route:
        print(f'{name}: map x={x:.3f} y={y:.3f} yaw={yaw:.4f}', flush=True)
    print('return_start: capture undocked starting pose at execution; then /robot5/dock')

    if not args.execute:
        print('Preview only. Use --execute after MAP-02 localisation and undocking.')
        return 0

    import fcntl
    import os
    import rclpy
    from action_msgs.msg import GoalStatus
    from irobot_create_msgs.action import Dock
    from irobot_create_msgs.msg import DockStatus
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid
    from rclpy.action import ActionClient
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from tf2_ros import Buffer, TransformException, TransformListener

    lock = open(f'/tmp/idc_robot5_route_{os.getuid()}.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another robot5 route process is already running on this host.')
        return 1

    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}

    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node(
        'agv_route_client',
        namespace='/robot5',
        cli_args=[
            '--ros-args',
            '-r', '/tf:=/robot5/tf',
            '-r', '/tf_static:=/robot5/tf_static',
        ],
    )

    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
    dock_client = ActionClient(node, Dock, 'dock')
    buffer = Buffer()
    listener = TransformListener(buffer, node)

    dock_state = None
    map_msg = None

    def on_dock(msg):
        nonlocal dock_state
        dock_state = msg.is_docked

    def on_map(msg):
        nonlocal map_msg
        map_msg = msg

    dock_subscription = node.create_subscription(
        DockStatus, 'dock_status', on_dock, qos_profile_sensor_data
    )

    map_qos = QoSProfile(depth=1)
    map_qos.reliability = ReliabilityPolicy.RELIABLE
    map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
    map_subscription = node.create_subscription(OccupancyGrid, 'map', on_map, map_qos)

    handle = None
    result = None

    def wait(future, timeout, interruptible=True):
        deadline = time.monotonic() + timeout
        while rclpy.ok() and time.monotonic() < deadline:
            if future.done():
                return True
            if interruptible and stopped:
                return False
            rclpy.spin_once(node, timeout_sec=0.1)
        return future.done()

    def cancel():
        if handle is None or (result is not None and result.done()):
            return
        node.get_logger().warning('Cancelling current goal; no subsequent goal will be sent.')
        response = handle.cancel_goal_async()
        wait(response, 5.0, interruptible=False)
        if result is not None and wait(result, 5.0, interruptible=False):
            node.get_logger().info(f'Goal terminal status: {result.result().status}')
        else:
            node.get_logger().error('STOP UNCONFIRMED: use the physical stop button and check Nav2.')

    def perform(action_client, goal, timeout, require_docked=False):
        nonlocal handle, result
        if stopped:
            return False

        handle, result = None, None
        pending = action_client.send_goal_async(goal)

        if not wait(pending, 15.0, interruptible=False):
            node.get_logger().error('Goal acceptance unknown. Use physical stop; do not restart yet.')
            return False

        handle = pending.result()
        if not handle.accepted:
            node.get_logger().error('Goal rejected. Route stopped.')
            return False

        result = handle.get_result_async()
        if stopped or not wait(result, timeout):
            cancel()
            return False

        status = result.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            node.get_logger().error(f'Goal failed/cancelled: status={status}. Route stopped.')
            return False

        return not require_docked or bool(result.result().result.is_docked)

    def navigate(waypoint):
        if stopped:
            return False

        name, x, y, yaw = waypoint
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = node.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)

        node.get_logger().info(f'GO {name}: ({x}, {y}, {yaw})')
        success = perform(client, goal, args.goal_timeout)

        if success:
            node.get_logger().info(f'ARRIVED {name}')
        return success

    def inspect(rack_id):
        node.get_logger().info(f'INSPECT PLACEHOLDER {rack_id}: waiting {args.dwell}s')
        # Phase-1 integration point for camera / door / LED inspection.
        deadline = time.monotonic() + args.dwell
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        return rclpy.ok() and not stopped

    def dock():
        node.get_logger().info('DOCK: handing control to Create 3 docking action')
        return perform(dock_client, Dock.Goal(), args.dock_timeout, require_docked=True)

    try:
        # Verify the namespaced MAP-02 before sending any motion goal.
        deadline = time.monotonic() + 5.0
        while rclpy.ok() and not stopped and map_msg is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)

        if map_msg is None:
            node.get_logger().error('No /robot5/map received. No motion sent.')
            return 1

        if not map_matches(map_msg):
            info = map_msg.info
            node.get_logger().error(
                'Wrong map loaded. Expected MAP-02 '
                f"res={EXPECTED_MAP['resolution']} "
                f"{EXPECTED_MAP['width']}x{EXPECTED_MAP['height']} "
                f"origin=({EXPECTED_MAP['origin_x']}, {EXPECTED_MAP['origin_y']}), "
                f'got res={info.resolution} {info.width}x{info.height} '
                f'origin=({info.origin.position.x}, {info.origin.position.y}). '
                'No motion sent.'
            )
            return 1

        node.get_logger().info('MAP-02 metadata verified.')

        # Start only after robot5 has undocked near its configured lower dock.
        deadline = time.monotonic() + 20.0
        start = None
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                transform = buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            except TransformException:
                continue

            age = (
                node.get_clock().now()
                - rclpy.time.Time.from_msg(transform.header.stamp)
            ).nanoseconds / 1e9
            if dock_state is not False or not (-0.5 <= age <= 2.0):
                continue

            t = transform.transform.translation
            q = transform.transform.rotation
            dock_pose = config['docks']['robot5']

            if math.hypot(
                t.x - float(dock_pose['x']),
                t.y - float(dock_pose['y']),
            ) > 0.8:
                node.get_logger().error(
                    'Start must be within 0.8m of the MAP-02 robot5 dock. No motion sent.'
                )
                return 1

            yaw = math.atan2(
                2 * (q.w * q.z + q.x * q.y),
                1 - 2 * (q.y * q.y + q.z * q.z),
            )
            start = ('return_start', t.x, t.y, yaw)
            break

        if start is None:
            node.get_logger().error('No fresh map pose and undocked status. No motion sent.')
            return 1

        node.get_logger().info(f'CAPTURED undocked return pose: {start}')
        route.append(start)

        if not dock_client.wait_for_server(timeout_sec=5.0):
            node.get_logger().error('Dock action unavailable. No motion sent.')
            return 1

        deadline = time.monotonic() + 30.0
        while not stopped and time.monotonic() < deadline:
            if client.wait_for_server(timeout_sec=0.2):
                break
        else:
            node.get_logger().error('Nav2 unavailable or interrupted; no goal sent.')
            return 1

        success = run_patrol(navigate, inspect, dock, route)
        print(
            'PATROL COMPLETE: robot5 Z4/Z3, 28 rack stops; DOCK SUCCEEDED and is_docked=true.'
            if success else 'ROUTE INCOMPLETE.',
            flush=True,
        )
        return 0 if success else 1

    finally:
        try:
            cancel()
        finally:
            map_subscription.destroy()
            dock_subscription.destroy()
            listener = None
            dock_client.destroy()
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
