# idc_web

W-owned control/web workspace. The source tree is kept together under `idc_web`, while deployment remains split according to ADR-001.

## Structure

```text
idc_web/
├── idc_bridge/  # ROS 2 ament_python package; runs on PC3
├── backend/     # FastAPI + PostgreSQL + MQTT; runs on PC4
└── frontend/    # React + Vite; runs on PC4
```

`src/idc_web/COLCON_IGNORE` is intentionally not used because colcon must discover the nested `idc_bridge` package. `backend/COLCON_IGNORE` and `frontend/COLCON_IGNORE` keep the Web-only trees out of colcon package discovery.

The repository location does not change the deployment boundary: `idc_bridge` participates in ROS 2 on PC3, while PC4 remains ROS-free.

## ROS ↔ MQTT bridge (PC3)

Build and verify discovery from the workspace root:

```bash
colcon list | grep idc_bridge
colcon build --symlink-install --packages-select idc_bridge
source install/setup.bash
```

Run the existing battery bridge for a robot namespace:

```bash
ros2 run idc_bridge mqtt_bridge --ros-args \
  -p robot_namespace:=/robot5 \
  -p mqtt_broker_host:=192.168.107.124 \
  -p mqtt_broker_port:=1883
```

The current migrated bridge preserves the previous `idc_server/mqtt_bridge.py` battery path. BRG-01 pose/state/event/command expansion is handled as the next bridge integration work; this migration only restores the ROS↔MQTT package boundary removed with `idc_server`.

## Backend (PC4)

Create the local environment under `backend/`:

```bash
cd src/idc_web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run FastAPI from `src/idc_web` so the `backend` package is importable:

```bash
cd src/idc_web
source backend/.venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Frontend (PC4)

```bash
cd src/idc_web/frontend
npm install
npm run dev -- --host 0.0.0.0
```
