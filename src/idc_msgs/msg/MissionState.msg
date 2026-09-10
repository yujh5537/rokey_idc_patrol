# MissionState.msg — mission_manager(PC3) → perception·Event_engine·bridge, 2Hz (SDD 4.2.3)
# 토픽: /robotN/mission/state
string  robot_id
string  state             # INIT | UNDOCK | NAVIGATE | FACE | INSPECT | MARKER_CHECK | RESUME | RETURN | DOCK | DONE | ERROR
string  zone_id           # 현재 구역
string  expected_rack_id  # INSPECT·MARKER_CHECK 중 기대 랙, 그 외 ""
int32   rack_idx          # 진행 n
int32   rack_total        # 총 개수
float32 battery
string  note              # 상태 메모 (예: "STOPPED")
