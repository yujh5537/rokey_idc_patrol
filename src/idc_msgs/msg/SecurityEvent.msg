# SecurityEvent.msg — Event_engine(PC3) → idc_bridge, 이벤트당 1회 (SDD 4.2.3)
# 토픽: /event/events   ※ severity·evidence·detail_json 없음 (SRD SR-F19: 증적 저장 안 함)
std_msgs/Header header
string  type              # "E5" (도어 개방)
string  robot_id
string  zone_id
string  rack_id
geometry_msgs/Point position   # 랙 좌표 (map) — racks.yaml 조회
string  basis             # "yolo" | "marker_missing"
float32 open_ratio        # 응시 구간 open 비율
int32   frames            # 응시 구간 door 관측 프레임 수 (open_ratio × frames = open 프레임 수, 확정 기준 ≥10)
bool    marker_checked    # MARKER_CHECK 수행 여부
