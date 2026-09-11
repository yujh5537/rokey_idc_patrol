#!/usr/bin/env python3
"""Three ordered map goals for robot11. Default: print only, no ROS imports."""
import argparse
import math
import signal
import time

# Arrival headings chosen for this demo; Z4 preserves entry_pose.yaw.
ROUTE = (
    ('dock_midpoint', 0.270, 2.625, -math.pi / 2),
    ('z2_z3_midpoint', 1.400, 2.800, 0.0),
    ('z4_entry', 1.400, 0.700, 0.0),
)


def run_route(navigate, pause, route=ROUTE):
    """Advance only after confirmed success and an uninterrupted dwell."""
    for waypoint in route:
        if not navigate(waypoint) or not pause():
            return False
    return True


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='send physical motion goals')
    parser.add_argument('--goal-timeout', type=positive, default=180.0)
    parser.add_argument('--dwell', type=positive, default=2.0)
    args = parser.parse_args()
    for name, x, y, yaw in ROUTE:
        print(f'{name}: map x={x:.3f} y={y:.3f} yaw={yaw:.4f}', flush=True)
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

    # Avoid two copies on the same host; does not lock other clients/hosts.
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
    node = rclpy.create_node('agv_route_client', namespace='/robot11')
    client = ActionClient(node, NavigateToPose, 'navigate_to_pose')
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
        handle, result = None, None
        pending = client.send_goal_async(goal)
        # Resolve acceptance even after Ctrl+C, so a late accepted goal is cancelled.
        if not wait(pending, 15.0, interruptible=False):
            node.get_logger().error('Goal acceptance unknown. Use physical stop; do not restart yet.')
            return False
        handle = pending.result()
        if not handle.accepted:
            node.get_logger().error('Goal rejected. Route stopped.')
            return False
        result = handle.get_result_async()
        if stopped or not wait(result, args.goal_timeout):
            cancel()
            return False
        status = result.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            node.get_logger().error(f'Goal failed/cancelled: status={status}. Route stopped.')
            return False
        node.get_logger().info(f'ARRIVED {name}; dwell {args.dwell}s')
        return True

    def pause():
        deadline = time.monotonic() + args.dwell
        while rclpy.ok() and not stopped and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        return rclpy.ok() and not stopped

    try:
        deadline = time.monotonic() + 30.0
        while not stopped and time.monotonic() < deadline:
            if client.wait_for_server(timeout_sec=0.2):
                break
        else:
            node.get_logger().error('Nav2 unavailable or interrupted; no goal sent.')
            return 1
        success = run_route(navigate, pause)
        print('ROUTE COMPLETE: stopped at Z4.' if success else 'ROUTE INCOMPLETE.', flush=True)
        return 0 if success else 1
    finally:
        try:
            cancel()
        finally:
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
