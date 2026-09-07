from setuptools import find_packages, setup

package_name = 'idc_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'paho-mqtt'],
    zip_safe=True,
    maintainer='yujh5537',
    maintainer_email='yujh5537@users.noreply.github.com',
    description='ROS 2 to MQTT bridge for the IDC patrol control/web boundary (W)',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mqtt_bridge = idc_bridge.mqtt_bridge:main',
        ],
    },
)
