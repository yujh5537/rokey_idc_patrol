# Marker.msg — ArUco 마커 1건 (SDD 4.2.3)
# 발행: aruco_node(PER-02, A1)
# 사전: DICT_5X5_100, ID 1~56, 마커 실측 20mm (v4 TB-03). ID 화이트리스트 필터 필수
# ※ marker_length 파라미터는 재출력 결정 후 확정 (20mm 유지 시 0.02)
# ※ 마커 map 좌표는 MAP-01 수동 매핑 주행 중 기록 → NAV-03 patrol_planner 입력

int32 id                            # ID → rack_id 매핑표는 A1·A2 별도 PR (인터페이스 등급)
geometry_msgs/PoseStamped pose_cam  # 카메라 광학 프레임 기준 pose
float32 distance                    # 카메라~마커 거리 [m]
