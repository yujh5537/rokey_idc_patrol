# MarkerArray.msg — 한 프레임의 마커 검출 결과 (SDD 4.2.3)
# 토픽: /robotN/perception/aruco @10Hz
# 발행: aruco_node(PER-02, A1)
# 소비: led_classifier(PER-03, A1 — ROI 기준), patrol_planner(NAV-03, R2 — 마커 map 좌표 등록)
# ※ 이름이 visualization_msgs/MarkerArray 와 같으므로 import 시 반드시 패키지명을 붙일 것

std_msgs/Header header
Marker[] markers
