# MissionState.msg — 로봇 미션 상태 (SDD 4.2.3)
# 토픽: /robotN/mission/state @2Hz  (N = robot5 | robot2)
# 발행: mission_manager(MIS-01/03, R3)
# 소비: fleet_coordinator(MIS-04, R3), ros2_mqtt_bridge(BRG-01, W → MQTT 2Hz) → PC4 서버·UI(SRV-02)
# ※ SDD 4.2.3 원문에 Header 가 없음 — 리뷰 항목 ① 참조

string robot_id
# 상태값 목록. 값 집합은 확장 대비로 유지하되, MVP 런타임에서 사용하지 않는 값이 있음.
#   INIT|EXPLORE|WAIT_MERGE|LOCALIZE|PLAN|PATROL|VERIFY|RETURN|DOCKING|CHARGING|ERROR|RELOCALIZE
#   [v5] EXPLORE·WAIT_MERGE = MVP 미사용. 지도는 사전 수동 SLAM(MAP-01)으로 만들어 병합본을 로드하므로
#        런타임 전이는 LOCALIZE→PLAN→PATROL→(VERIFY)→RETURN→DOCKING 이다.
#   [확장] RELOCALIZE = EXT-01 재측위 스텁
string state
int32 waypoint_idx           # 현재 순찰 웨이포인트 인덱스 (0-based). 순찰 중 아니면 -1
int32 waypoint_total         # 이번 순찰의 전체 웨이포인트 수. 순찰 중 아니면 0
float32 battery              # 0.0~1.0
string note                  # 예외 사유 자유 필드. 예: "RELOC_FAIL", "AP_LOST"
