# ObjectArray.msg — 한 프레임의 인식 결과 묶음 (SDD 4.2.3)
# 토픽: /robotN/perception/objects @10Hz
# 발행: detection_localizer(PER-05, A2)  소비: event_engine(A3), control_server(W)
# header.stamp 는 원본 이미지 stamp 를 그대로 승계할 것 (tf 시각 정합 — SR-F15)

std_msgs/Header header
string robot_id            # "robot1" | "robot2" — 네임스페이스와 동일 문자열
Object[] objects
