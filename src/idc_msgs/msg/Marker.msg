# Marker.msg — ArUco 마커 1건 (SDD 4.2.3)
# 발행: aruco_node(PER-02, A1)

int32 id                            # DICT_4X4_50 마커 ID (TB-03 마커 ID표 기준)
geometry_msgs/PoseStamped pose_cam  # 카메라 광학 프레임 기준 pose
float32 distance                    # 카메라~마커 거리 [m]
