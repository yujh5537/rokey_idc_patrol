# Object.msg — 인식된 개체 1건 (SDD 4.2.3)
# 발행: detection_localizer(PER-04/05, A2) → ObjectArray에 담겨 나감
# 소비: event_engine(EVT-01/02, A3), control_server(SRV-02, W)

# class_name 허용값 (REP-02 확정 — data.yaml 클래스와 1:1이 아님)
#   YOLO 2종 (DAT-01 data.yaml, 순서 고정):  0 rack_door_open | 1 rack_door_closed
#   LED 판정 3종 (led_classifier PER-03, A1 — YOLO 아님, 마커 ROI HSV 2색 판정 결과):
#       led_green | led_red | led_off
#   ※ led_off 는 값으로 유지하되 E7 이벤트화하지 않음(로그·ROI 진단용) — PM 확정 9/6
#   ※ PER-05에서 YOLO 결과와 LED 결과를 rack_id 기준으로 병합해 같은 배열에 실음
string class_name

int32 track_id                      # ByteTrack 트랙 ID. 미추적 시 -1
float32 confidence                  # 0.0~1.0
geometry_msgs/PoseStamped map_pose  # frame_id="map". depth 역투영 → tf → map (SR-F15)
bool low_confidence                 # true = LiDAR 거리와 0.3m 이상 불일치 (SR-F15)
string zone_id                      # zones.yaml 폴리곤 판정 결과. 미판정 ""
string rack_id                      # 최근접 랙(0.6m 이내). 없으면 ""
string identity                     # "" | person_id | "unknown" — 얼굴 인식은 확장(EXT-03), MVP는 항상 ""
