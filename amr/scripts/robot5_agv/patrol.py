#!/usr/bin/env python3
"""Robot5 Z4/Z3 patrol on MAP-02 and return docking. Default: preview only.

Same design as scripts/robot11_agv/patrol.py, mirrored for robot5:
  * namespace /robot5, lock /tmp/idc_robot5_route_<uid>.lock
  * patrol zones Z4 -> Z3 (robot5 is docked below the middle wall)
  * 28 rack stops from racks.yaml patrol_routes.robot5, then Create 3 docking

Localization (AMCL) and Nav2 must already be running for /robot5; this script
only sends NavigateToPose / Spin / Undock / Dock goals in the map frame.
"""

import argparse
import math
import signal
import time
from pathlib import Path


def _racks_yaml():
    """Locate <repo>/src/idc_bringup/config/racks.yaml by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        candidate = parent / 'src/idc_bringup/config/racks.yaml'
        if candidate.exists():
            return candidate
    raise RuntimeError('racks.yaml not found (expected <repo>/src/idc_bringup/config/racks.yaml)')


CONFIG = _racks_yaml()


EXPECTED_ROBOT5_ROUTE = [
    'R56', 'R55', 'R54', 'R53', 'R52', 'R51', 'R50',
    'R43', 'R44', 'R45', 'R46', 'R47', 'R48', 'R49',
    'R42', 'R41', 'R40', 'R39', 'R38', 'R37', 'R36',
    'R29', 'R30', 'R31', 'R32', 'R33', 'R34', 'R35',
]


# Exact MAP-02 loaded by:
# $(ros2 pkg prefix idc_bringup)/share/idc_bringup/maps/idc_testbed.yaml
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
    """Build the robot5 Z4/Z3 route directly in the MAP-02 map frame."""
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

    # robot5 is docked below the middle wall (x=0.8, opening y=2.4..3.2).
    # Undock near robot5 dock (0.27, 0.33)
    #   -> midpoint of the two docks, aligned with the wall opening
    #   -> cross the opening to the rack side at trunk_x
    #   -> patrol Z4 first, then Z3.
    route = [
        ('dock_midpoint', 0.270, 2.625, math.pi / 2),
        ('mid_wall_crossing', 1.400, 2.800, 0.0),
    ]

    for zone in ('Z4', 'Z3'):
        entry = config['zones'][zone]['entry_pose']
        route.append(pose(zone + '_entry', entry))

        zone_ids = [rid for rid in ids if racks[rid]['zone_id'] == zone]
        if len(zone_ids) != 14:
            raise ValueError(f'Expected 14 racks in {zone}')

        route.extend(pose(rid, racks[rid]['inspect_pose']) for rid in zone_ids)
        route.append(pose(zone + '_exit', dict(entry, yaw=math.pi)))

    # Return through the same major waypoints. The exact undock pose is
    # appended at runtime before Create 3 docking.
    route.extend([
        ('return_mid_wall_crossing', 1.400, 2.800, math.pi),
        ('return_dock_midpoint', 0.270, 2.625, -math.pi / 2),
    ])
    return route


def run_patrol(navigate, inspect, dock, route):
    """Continue only when Nav2 reports successful arrival.

    Rack inspection is executed after each rack waypoint.
    """
    for waypoint in route:
        if not navigate(waypoint):
            return False
        if waypoint[0].startswith('R') and not inspect(waypoint[0]):
            return False
    return dock()


REQUIRED_NODES = (
    'map_server', 'amcl', 'controller_server', 'smoother_server',
    'planner_server', 'route_server', 'behavior_server', 'velocity_smoother',
    'collision_monitor', 'bt_navigator', 'waypoint_follower', 'docking_server',
)


def ensure_undocked(is_docked, undock, confirm):
    """Unknown status never authorizes movement; verify after undocking."""
    if is_docked is None:
        return False
    if is_docked:
        return undock() and confirm()
    return confirm()


RACK_TRAVEL_TOLERANCE = 0.08
TURN_TOLERANCE = math.radians(8)


def angle_difference(target, actual):
    return math.atan2(math.sin(target - actual), math.cos(target - actual))


def visit_rack(waypoint, read_pose, turn, move):
    """Separate heading, travel and rack-facing actions; no precision rejection.

    Nearby goals (including opposite faces at the same XY) only require a turn.
    Any failed action blocks all subsequent stages and the dwell in run_patrol.
    """
    name, x, y, yaw = waypoint
    actual = read_pose()
    if actual is None:
        return False
    dx, dy = x - actual[0], y - actual[1]
    if math.hypot(dx, dy) > RACK_TRAVEL_TOLERANCE:
        heading = math.atan2(dy, dx)
        if not turn(name + ':TURN_TO_TRAVEL', heading):
            return False
        if not move((name + ':MOVE', x, y, heading)):
            return False
    return turn(name + ':FACE_RACK', yaw)


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
    parser.add_argument('--undock-only', action='store_true',
                        help='with --execute: undock, then exit for localization setup')
    parser.add_argument('--ready-timeout', type=positive, default=180.0,
                        help='seconds to allow for localization and Nav2 preparation')
    args = parser.parse_args()

    import yaml

    with CONFIG.open() as stream:
        config = yaml.safe_load(stream)

    route = build_route(config)
    for name, x, y, yaw in route:
        print(f'{name}: map x={x:.3f} y={y:.3f} yaw={yaw:.4f}', flush=True)
    print('return_start: capture undocked starting pose at execution; then /robot5/dock')

    if not args.execute:
        print('Preview only. Use --execute to undock and patrol; '
              '--execute --undock-only for staged setup.')
        return 0

    import fcntl
    import os
    import rclpy
    from action_msgs.msg import GoalStatus
    from irobot_create_msgs.action import Dock, Undock
    from irobot_create_msgs.msg import DockStatus
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose, Spin
    from nav_msgs.msg import OccupancyGrid
    from sensor_msgs.msg import LaserScan
    from rclpy.action import ActionClient
    from rclpy.qos import (
        DurabilityPolicy,
        QoSProfile,
        ReliabilityPolicy,
        qos_profile_sensor_data,
    )
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
    spin_client = ActionClient(node, Spin, 'spin')
    undock_client = ActionClient(node, Undock, 'undock')
    state_clients = {name: node.create_client(GetState, name + '/get_state')
                     for name in REQUIRED_NODES}
    last_scan = None

    def on_scan(msg):
        nonlocal last_scan
        last_scan = msg.header.stamp

    scan_subscription = node.create_subscription(
        LaserScan, 'scan', on_scan, qos_profile_sensor_data)

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

    # Create 3 republishes a retained state, not necessarily a periodic sample.
    # Request history so a client started after undocking receives the last state.
    dock_qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    dock_subscription = node.create_subscription(
        DockStatus, 'dock_status', on_dock, dock_qos
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
            node.get_logger().error(f'Action interrupted or timed out after limit={timeout}s')
            cancel()
            return False

        status = result.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            node.get_logger().error(
                f'Goal failed/cancelled: status={status}, result={result.result().result}. '
                'Route stopped.'
            )
            return False

        return not require_docked or bool(result.result().result.is_docked)

    def send_navigation(waypoint):
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

    def read_pose():
        deadline = time.monotonic() + 3.0
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                tf = buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
                age = (node.get_clock().now() - rclpy.time.Time.from_msg(tf.header.stamp)).nanoseconds / 1e9
                t, q = tf.transform.translation, tf.transform.rotation
                yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
                pose = (t.x, t.y, yaw)
                if -0.5 <= age <= 2.0 and all(math.isfinite(v) for v in pose):
                    return pose
            except TransformException:
                pass
        node.get_logger().error('No fresh robot pose for rack movement. Route stopped.')
        return None

    def turn(label, target_yaw):
        actual = read_pose()
        if actual is None:
            return False
        delta = angle_difference(target_yaw, actual[2])
        node.get_logger().info(
            f'{label}: target={math.degrees(target_yaw):.1f}deg, turn={math.degrees(delta):.1f}deg')
        if abs(delta) <= TURN_TOLERANCE:
            return not stopped
        goal = Spin.Goal()
        goal.target_yaw = float(delta)
        goal.time_allowance.sec = 30
        return perform(spin_client, goal, 35.0)

    def navigate(waypoint):
        if stopped:
            return False
        if waypoint[0] not in EXPECTED_ROBOT5_ROUTE:
            return send_navigation(waypoint)
        success = visit_rack(waypoint, read_pose, turn, send_navigation)
        if success:
            node.get_logger().info(f'ARRIVED {waypoint[0]}: rack-facing stage complete')
        return success

    def inspect(rack_id):
        node.get_logger().info(f'DWELL {rack_id} (no camera/YOLO): waiting {args.dwell}s')
        # Phase-1 route integration point:
        # TODO: MissionState FACE -> INSPECT -> camera capture -> door detection
        #       -> LED classification -> RESUME / MARKER_CHECK
        deadline = time.monotonic() + args.dwell
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        return rclpy.ok() and not stopped

    def dock():
        node.get_logger().info('DOCK: handing control to Create 3 docking action')
        return perform(dock_client, Dock.Goal(), args.dock_timeout, require_docked=True)

    def confirm_undocked():
        deadline = time.monotonic() + 10.0
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if dock_state is False:
                return True
        return False

    def undock():
        if not undock_client.wait_for_server(timeout_sec=5.0):
            node.get_logger().error('Undock action unavailable.')
            return False
        node.get_logger().info('UNDOCK: Create 3 action; clear the dock exit area.')
        if not perform(undock_client, Undock.Goal(), args.dock_timeout):
            return False
        if result.result().result.is_docked:
            node.get_logger().error('Undock action succeeded but reports is_docked=true.')
            return False
        return True

    def wait_ready():
        deadline = time.monotonic() + args.ready_timeout
        node.get_logger().info('WAIT READY: align MAP-02 pose in RViz, then start Nav2.')
        last_report = 0.0
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            pending_nodes = set()
            for name, service in state_clients.items():
                if stopped or time.monotonic() >= deadline:
                    return False
                if not service.service_is_ready():
                    pending_nodes.add(name)
                    continue
                future = service.call_async(GetState.Request())
                if not wait(future, min(1.0, max(0.0, deadline - time.monotonic()))):
                    service.remove_pending_request(future)
                    pending_nodes.add(name)
                elif future.result().current_state.id != 3:
                    pending_nodes.add(name)
            scan_ok = False
            if last_scan is not None:
                age = (node.get_clock().now() - rclpy.time.Time.from_msg(last_scan)).nanoseconds / 1e9
                scan_ok = -0.5 <= age <= 1.0
            if not pending_nodes and scan_ok:
                node.get_logger().info('READY: all required lifecycle nodes active and scan fresh.')
                return True
            if time.monotonic() - last_report >= 5.0:
                node.get_logger().warning(f'Not ready: nodes={sorted(pending_nodes)}, fresh_scan={scan_ok}')
                last_report = time.monotonic()
            rclpy.spin_once(node, timeout_sec=0.2)
        node.get_logger().error('Preparation timed out/interrupted. No navigation goal sent.')
        return False

    try:
        deadline = time.monotonic() + 10.0
        while rclpy.ok() and not stopped and dock_state is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if stopped or not ensure_undocked(dock_state, undock, confirm_undocked):
            node.get_logger().error('Undocking/status confirmation failed. Patrol blocked.')
            return 1
        if args.undock_only:
            node.get_logger().info('UNDOCK COMPLETE: set actual pose in RViz, start Nav2, then run --execute.')
            return 0
        if not wait_ready():
            return 1

        # 1. MAP-02 verification
        deadline = time.monotonic() + 5.0
        while rclpy.ok() and not stopped and map_msg is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)

        if map_msg is None:
            node.get_logger().error('No /robot5/map received. No navigation goal sent.')
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
                'No navigation goal sent.'
            )
            return 1

        node.get_logger().info('MAP-02 metadata verified.')

        # 2. Capture undocked robot5 starting pose
        deadline = time.monotonic() + 20.0
        start = None
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                transform = buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            except TransformException:
                continue

            age = (
                node.get_clock().now() - rclpy.time.Time.from_msg(transform.header.stamp)
            ).nanoseconds / 1e9
            if dock_state is not False or not (-0.5 <= age <= 2.0):
                continue

            t = transform.transform.translation
            q = transform.transform.rotation
            dock_pose = config['docks']['robot5']

            if math.hypot(t.x - float(dock_pose['x']), t.y - float(dock_pose['y'])) > 0.8:
                node.get_logger().error(
                    'Start must be within 0.8m of the MAP-02 robot5 dock. No navigation goal sent.')
                return 1

            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
            start = ('return_start', t.x, t.y, yaw)
            break

        if start is None:
            node.get_logger().error('No fresh map pose and undocked status. No navigation goal sent.')
            return 1

        node.get_logger().info(f'CAPTURED undocked return pose: {start}')
        route.append(start)

        # 3. Check Create 3 Dock action
        if not dock_client.wait_for_server(timeout_sec=5.0):
            node.get_logger().error('Dock action unavailable. No navigation goal sent.')
            return 1

        # 4. Check Nav2
        deadline = time.monotonic() + 30.0
        while not stopped and time.monotonic() < deadline:
            if client.wait_for_server(timeout_sec=0.2):
                break
        else:
            node.get_logger().error('Nav2 unavailable or interrupted; no goal sent.')
            return 1

        # 5. Robot5 Z4 / Z3 patrol
        if not spin_client.wait_for_server(timeout_sec=5.0):
            node.get_logger().error('Nav2 spin action unavailable. No navigation goal sent.')
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
            spin_client.destroy()
            scan_subscription.destroy()
            undock_client.destroy()
            for service in state_clients.values():
                node.destroy_client(service)
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
