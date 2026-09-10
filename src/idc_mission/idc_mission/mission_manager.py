#!/usr/bin/env python3
"""mission_manager — 골격(스텁). 실제 구현은 해당 작업 ID STEP에서 채움.

규칙: 네임스페이스는 코드에 하드코딩하지 않는다. launch 에서 namespace:=robot1 로 주입하면
이 노드의 상대 토픽 'oakd/rgb/...' 가 자동으로 '/robot1/oakd/rgb/...' 로 해석됨.
"""
import rclpy
from rclpy.node import Node


class MissionManager(Node):
    def __init__(self):
        super().__init__('mission_manager')
        self.get_logger().info(f'mission_manager 기동 — ns={self.get_namespace()} (스텁)')


def main(args=None):
    rclpy.init(args=args)
    node = MissionManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
