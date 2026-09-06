# Candidate.msg — 이상 "후보" (확정 전, 임계값 τ1=0.5) (SDD 4.2.3)
# 토픽: /robotN/mission/candidate
# 발행: event_engine(EVT-01/02, A3)  소비: mission_manager VERIFY 서브루틴(MIS-05, R3)
# 흐름: ObjectArray → Candidate → (근접 확인) → SecurityEvent

std_msgs/Header header
string type                  # "E5"(랙 도어 개방) | "E7"(LED 이상) — MVP 범위 2종
string rack_id
string zone_id
geometry_msgs/Point position # map 프레임 좌표. VERIFY 접근 목표 산출 기준(정면 0.6m)
float32 confidence
