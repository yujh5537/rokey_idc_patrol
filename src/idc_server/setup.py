# setup.py — ament_python 패키지 빌드 정의.
# entry_points.console_scripts 에 등록된 이름이 `ros2 run idc_server <노드명>` 으로 실행됨.
from glob import glob
import os
from setuptools import find_packages, setup

package_name = 'idc_server'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # launch/·config/ 파일을 install 공간에 복사 → ros2 launch / get_package_share_directory 로 접근
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'paho-mqtt'],
    zip_safe=True,
    maintainer='yujh5537',
    maintainer_email='yujh5537@users.noreply.github.com',
    description='Flask+SocketIO+rclpy 관제 서버·UI (W)',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'control_server = idc_server.control_server:main',
            'mqtt_bridge = idc_server.mqtt_bridge:main', # mqtt bridge
            'init_db = idc_server.init_db:main',
            'audit = idc_server.audit:main'
        ],
    },
)
