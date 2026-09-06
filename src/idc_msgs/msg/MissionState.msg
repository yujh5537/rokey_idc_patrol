# MissionState.msg — 로봇 미션 상태 (SDD 4.2.3)
# 토픽: /robotN/mission/state @2Hz
# 발행: mission_manager(MIS-01/03, R3)
# 소비: fleet_coordinator(MIS-04, R3), control_server → robots 테이블·UI(SRV-02, W)
# ※ SDD 4.2.3 원문에 Header 가 없음 — 리뷰 항목 ① 참조

string robot_id
string state                 # INIT|EXPLORE|WAIT_MERGE|LOCALIZE|PLAN|PATROL|VERIFY|RETURN|DOCKING|CHARGING|ERROR|RELOCALIZE
int32 waypoint_idx           # 현재 순찰 웨이포인트 인덱스 (0-based). 순찰 중 아니면 -1
int32 waypoint_total         # 이번 순찰의 전체 웨이포인트 수. 순찰 중 아니면 0
float32 battery              # 0.0~1.0
string note                  # 예외 사유 자유 필드. 예: "RELOC_FAIL", "AP_LOST"
