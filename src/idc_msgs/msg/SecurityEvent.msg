# SecurityEvent.msg — 확정된 보안 이벤트 (임계값 τ2=0.7) (SDD 4.2.3)
# 토픽: /event/events (전역 — 네임스페이스 없음)
# 발행: E5 → mission_manager VERIFY 판정(MIS-05, R3) / E7 → event_engine 직접 발행(EVT-02, A3, VERIFY 미경유)
# 소비: ros2_mqtt_bridge(BRG-01/02, W) → PC4 FastAPI → PostgreSQL events + React UI(SRV-04/05)

std_msgs/Header header
string robot_id
string type                  # "E1".."E9". MVP는 E5(도어 개방), E7(LED 이상)만 사용
uint8 severity               # 1..4 (L1 정보 / L2 주의 / L3 경고 / L4 위험)
                             # SDD 5.6 판정 조건표: E5 = 3(L3), E7 = 2(L2). 발행하는 노드가 채운다
string zone_id
string rack_id
geometry_msgs/Point position # map 프레임
int64[] evidence_ids         # Snapshot 응답의 evidence_id 목록. 없으면 빈 배열
string detail_json           # 판정 근거 자유 필드(JSON 문자열). 예: {"votes":12,"frames":15,"led":"red"}
