cmake_minimum_required(VERSION 3.8)
project(idc_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

# REP-02 확정 인터페이스 (SDD 4.2.3) — 양 팀 리뷰 승인 후 변경 금지
set(msg_files
  "msg/Object.msg"
  "msg/ObjectArray.msg"
  "msg/Marker.msg"
  "msg/MarkerArray.msg"
  "msg/Candidate.msg"
  "msg/SecurityEvent.msg"
  "msg/MissionState.msg"
)
set(srv_files
  "srv/Snapshot.srv"
  "srv/GenerateRoute.srv"
  "srv/DockOrder.srv"
)
rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES std_msgs geometry_msgs sensor_msgs
)
ament_export_dependencies(rosidl_default_runtime)
ament_package()
