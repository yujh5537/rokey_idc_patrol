import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped
import math
import time

class Robot5PathExecutor(Node):
    def __init__(self):
        super().__init__('robot5_path_executor')
        self.publisher_ = self.create_publisher(TwistStamped, '/robot5/cmd_vel', 10)

        self.linear_speed = 0.15  # m/s
        self.angular_speed = 0.5  # rad/s

        # 지그재그 스캔 한 줄에 몇 번 0.2m씩 전진할지 (구간 길이에 맞춰 조정 가능)
        self.ZIGZAG_STEPS = 7

    def make_twist_stamped(self, linear_x=0.0, angular_z=0.0):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x = linear_x
        msg.twist.angular.z = angular_z
        return msg

    def move_straight(self, distance):
        duration = distance / self.linear_speed
        self.get_logger().info(f'직진 {distance}m 시작 (약 {duration:.2f}초)')
        start_time = time.time()
        while time.time() - start_time < duration:
            self.publisher_.publish(self.make_twist_stamped(linear_x=self.linear_speed))
            time.sleep(0.05)
        self.stop()

    def turn(self, angle_deg):
        # 양수: 왼쪽 회전, 음수: 오른쪽 회전
        angular = self.angular_speed if angle_deg > 0 else -self.angular_speed
        radians = abs(math.radians(angle_deg))
        duration = radians / self.angular_speed
        self.get_logger().info(f'회전 {angle_deg}도 시작 (약 {duration:.2f}초)')
        start_time = time.time()
        while time.time() - start_time < duration:
            self.publisher_.publish(self.make_twist_stamped(angular_z=angular))
            time.sleep(0.05)
        self.stop()

    def stop(self):
        self.publisher_.publish(self.make_twist_stamped())
        time.sleep(0.3)

    def pause(self, seconds):
        self.get_logger().info(f'{seconds}초 동안 정지')
        self.stop()
        time.sleep(seconds)

    def zigzag_scan_column(self, label):
        """
        한 구간(예: 6~8 사이)을 0.2m씩 전진하며 좌우 스캔.
        내려가며: 오른쪽90(스캔+정지) -> 왼쪽90(복귀) -> 0.2m 전진  (ZIGZAG_STEPS회)
        마지막 한 번 더 스캔 -> 180도 회전(반대편 스캔용) ->
        올라가며: 왼쪽90(복귀) -> 0.2m 전진 -> 오른쪽90(스캔+정지) (ZIGZAG_STEPS회)
        """
        self.get_logger().info(f'--- {label} 구간 지그재그 스캔 시작 ---')

        # 내려가는 패스
        for i in range(self.ZIGZAG_STEPS):
            self.turn(-90); self.pause(3.0)   # 오른쪽으로 90도 회전 후 3초 정지 (스캔)
            self.turn(90)                     # 왼쪽 90도 회전 (원래 방향 복귀)
            self.move_straight(0.2)           # 0.2m 전진

        # 구간 끝에서 마지막 스캔 + 180도 회전
        self.turn(-90); self.pause(3.0)       # 오른쪽으로 90도 회전 후 3초 정지
        self.turn(180); self.pause(3.0)       # 왼쪽으로 180도 회전 후 3초 정지

        # 올라가는 패스 (반대편 스캔)
        for i in range(self.ZIGZAG_STEPS):
            self.turn(90)                     # 왼쪽 90도 회전
            self.move_straight(0.2)           # 0.2m 전진
            self.turn(-90); self.pause(3.0)   # 오른쪽으로 90도 회전 후 3초 정지 (스캔)

        self.get_logger().info(f'--- {label} 구간 지그재그 스캔 완료 ---')

    def execute_path(self):
        self.get_logger().info('1. 언도킹 대기 및 준비')
        time.sleep(2.0)

        # 도크 -> 1번 -> 2번 -> 6번 -> 7번
        self.turn(90);  self.move_straight(2.46)   # -> 1번
        self.turn(-90); self.move_straight(0.77)   # -> 2번
        self.turn(-90); self.move_straight(2.10)   # -> 6번 (0.7 + 1.40, 3번은 경유만)
        self.turn(90);  self.move_straight(0.82)   # -> 7번

        # 6~8 구간 지그재그 스캔
        self.zigzag_scan_column('6~8')

        # 7 부근 -> 6번 -> 3번 -> 4번
        self.turn(90);  self.move_straight(0.82)   # -> 6번
        self.turn(-90); self.move_straight(1.40)   # -> 3번
        self.turn(-90); self.move_straight(0.82)   # -> 4번

        # 3~5 구간 지그재그 스캔 (동일 패턴)
        self.zigzag_scan_column('3~5')

        # 4 부근 -> 3번 -> 2번 -> 1번 (복귀)
        self.turn(90);  self.move_straight(0.82)   # -> 3번
        self.turn(-90); self.move_straight(0.70)   # -> 2번
        self.turn(90);  self.move_straight(0.77)   # -> 1번

        self.get_logger().info('모든 경로 주행이 완료되었습니다.')

def main(args=None):
    rclpy.init(args=args)
    executor = Robot5PathExecutor()
    executor.execute_path()
    executor.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
