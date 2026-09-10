# ObjectArray.msg — perception_node(PC1·PC2) → Event_engine·mission(PC3), 응시 구간 중 ≥5Hz (SDD 4.2.3)
# 토픽: /robotN/perception/objects
std_msgs/Header header
string   robot_id         # "robot5" | "robot11"
Object[] objects          # 현재 랙 1건 (화면 중앙 랙만)
