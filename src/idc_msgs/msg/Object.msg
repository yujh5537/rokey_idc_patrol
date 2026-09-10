# Object.msg — 현재 랙 1건 (SDD 4.2.3)
# 발행: perception_node(PC1·PC2)  구독: Event_engine·mission(PC3)
string  rack_id           # "R01".."R56" — 화면 중앙 마커 ID → "R%02d", 마커 없으면 기대 rack_id
string  zone_id           # "Z1".."Z4"
string  door_state        # "open" | "closed" (YOLO class)
float32 confidence        # YOLO conf
bool    marker_detected   # 기대 rack_id의 마커가 이 프레임에서 검출됐는지
