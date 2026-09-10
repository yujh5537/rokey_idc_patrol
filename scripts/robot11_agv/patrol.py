#!/usr/bin/env python3
"""Robot11 Z1/Z2 patrol and return docking. Default: preview only."""
import argparse
import math
import signal
import time

from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / 'src/idc_bringup/config/racks.yaml'

# MAP-02 -> Final SLAM map rigid transform.
# Keep racks.yaml as the MAP-02 source of truth and transform poses at runtime.
# Final map: maps/Final.yaml (0.05 m/px, origin [-3.523, -5.735, 0]).
MAP02_TO_FINAL_YAW = 3.21718836
MAP02_TO_FINAL_TX = 0.11410702
MAP02_TO_FINAL_TY = 0.26603952


def final_pose(name, x, y, yaw):
    """Transform a MAP-02 pose into the current Final SLAM-map frame."""
    x = float(x)
    y = float(y)
    yaw = float(yaw)
    c = math.cos(MAP02_TO_FINAL_YAW)
    s = math.sin(MAP02_TO_FINAL_YAW)
    final_x = c * x - s * y + MAP02_TO_FINAL_TX
    final_y = s * x + c * y + MAP02_TO_FINAL_TY
    final_yaw = math.atan2(
        math.sin(yaw + MAP02_TO_FINAL_YAW),
        math.cos(yaw + MAP02_TO_FINAL_YAW),
    )
    return (name, final_x, final_y, final_yaw)


def build_route(config):
    """Transform MAP-02 poses into the current Final SLAM map frame."""
    racks = {r['rack_id']: r for r in config['racks']}
    ids = config['patrol_routes']['robot11']
    if len(ids) != 28 or len(set(ids)) != 28:
        raise ValueError('Expected 28 distinct robot11 racks')

    def pose(name, data):
        values = tuple(float(data[k]) for k in ('x', 'y', 'yaw'))
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f'Invalid pose: {name}')
        return final_pose(name, *values)

    route = [
        final_pose('dock_midpoint', .270, 2.625, -math.pi / 2),
        final_pose('z2_z3_midpoint', 1.400, 2.800, 0.0),
    ]
    for zone in ('Z1', 'Z2'):
        entry = config['zones'][zone]['entry_pose']
        route.append(pose(zone + '_entry', entry))
        zone_ids = [rid for rid in ids if racks[rid]['zone_id'] == zone]
        if len(zone_ids) != 14:
            raise ValueError(f'Expected 14 racks in {zone}')
        route.extend(pose(rid, racks[rid]['inspect_pose']) for rid in zone_ids)
        route.append(pose(zone + '_exit', dict(entry, yaw=math.pi)))
    route.extend([
        final_pose('return_z2_z3_midpoint', 1.400, 2.800, math.pi),
        final_pose('return_dock_midpoint', .270, 2.625, math.pi / 2),
    ])
    return route


def pose_matches(actual, target):
    """Distinct 21cm-spaced rack stops; camera heading within 3 degrees."""
    dx, dy = actual[0] - target[0], actual[1] - target[1]
    angle = math.atan2(
        math.sin(actual[2] - target[2]),
        math.cos(actual[2] - target[2]),
    )
    return math.hypot(dx, dy) <= 0.08 and abs(angle) <= math.radians(3)


def run_patrol(navigate, inspect, dock, route):
    """Never inspect before arrival, or return/dock after a failed stage."""
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
    print('return_start: capture undocked starting pose at execution; then /robot11/dock')
    if not args.execute:
        print('Preview only. Use --execute after localisation and undocking.')
        return 0

    import fcntl
    import os
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.signals import SignalHandlerOptions
    from nav2_msgs.action import NavigateToPose
    from action_msgs.msg import GoalStatus
    from irobot_create_msgs.action import Dock
    from irobot_create_msgs.msg import DockStatus
    from tf2_ros import Buffer, TransformListener, TransformException
    from rclpy.qos import qos_profile_sensor_data

    lock = open(f'/tmp/idc_robot11_route_{os.getuid()}.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another route process is already running on this host.')
        return 1
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node(
        'agv_route_client',
        namespace='/robot11',
        cli_args=['--ros-args', '-r', '/tf:=/robot11/tf', '-r', '/tf_static:=/robot11/tf_static'],
    )
    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
    dock_client = ActionClient(node, Dock, 'dock')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    dock_state = None

    def on_dock(msg):
        nonlocal dock_state
        dock_state = msg.is_docked

    dock_subscription = node.create_subscription(DockStatus, 'dock_status', on_dock, qos_profile_sensor_data)
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

    def navigate(waypoint):
        nonlocal handle, result
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
        if success and name.startswith('R'):
            try:
                tf = buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
                age = (node.get_clock().now() - rclpy.time.Time.from_msg(tf.header.stamp)).nanoseconds / 1e9
                t, q = tf.transform.translation, tf.transform.rotation
                heading = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
                success = -0.5 <= age <= 2.0 and pose_matches((t.x, t.y, heading), (x, y, yaw))
            except TransformException:
                success = False
            if not success:
                node.get_logger().error('Rack alignment outside 0.08m / 3deg or TF unavailable. Stopped; check localisation and goal checker tolerances.')
        if success:
            node.get_logger().info(f'ARRIVED {name}')
        return success

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

    def inspect(rack_id):
        node.get_logger().info(f'INSPECT PLACEHOLDER {rack_id}: aligned; waiting {args.dwell}s')
        deadline = time.monotonic() + args.dwell
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        return rclpy.ok() and not stopped

    def dock():
        node.get_logger().info('DOCK: handing control to Create 3 docking action')
        return perform(dock_client, Dock.Goal(), args.dock_timeout, require_docked=True)

    try:
        deadline = time.monotonic() + 20.0
        start = None
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            try:
                transform = buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            except TransformException:
                continue
            age = (node.get_clock().now() - rclpy.time.Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
            if dock_state is not False or not (-0.5 <= age <= 2.0):
                continue
            t, q = transform.transform.translation, transform.transform.rotation
            dock_pose = config['docks']['robot11']
            _, dock_x, dock_y, _ = final_pose('robot11_dock', dock_pose['x'], dock_pose['y'], dock_pose['yaw'])
            if math.hypot(t.x - dock_x, t.y - dock_y) > 0.8:
                node.get_logger().error('Start must be near robot11 dock (within 0.8m). No motion sent.')
                return 1
            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
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
        print('PATROL COMPLETE: 28 rack stops; DOCK SUCCEEDED and is_docked=true.' if success else 'ROUTE INCOMPLETE.', flush=True)
        return 0 if success else 1
    finally:
        try:
            cancel()
        finally:
            dock_client.destroy()
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
