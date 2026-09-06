# Object.msg — 인식된 개체 1건 (SDD 4.2.3)
# 발행: detection_localizer(PER-04/05, A2) → ObjectArray에 담겨 나감
# 소비: event_engine(EVT-01/02, A3), control_server(SRV-02, W)

# YOLO 클래스명. DAT-01 data.yaml의 클래스명과 문자열이 정확히 일치해야 함.
#   rack_door_open | rack_door_closed | person | obj_bag | obj_box
# LED 상태는 led_classifier(PER-03, A1)가 rack 속성으로 병합 → led_green | led_red | led_off
string class_name

int32 track_id                      # ByteTrack 트랙 ID. 미추적 시 -1
float32 confidence                  # 0.0~1.0
geometry_msgs/PoseStamped map_pose  # frame_id="map". depth 역투영 → tf → map (SR-F15)
bool low_confidence                 # true = LiDAR 거리와 0.3m 이상 불일치 (SR-F15)
string zone_id                      # zones.yaml 폴리곤 판정 결과. 미판정 ""
string rack_id                      # 최근접 랙(0.6m 이내). 없으면 ""
string identity                     # "" | person_id | "unknown" — 얼굴 인식은 확장(EXT-03), MVP는 항상 ""
