# idc_web

PC4 Web/Data Plane workspace.

## Structure

```text
idc_web/
├── backend/   # FastAPI + PostgreSQL + MQTT
└── frontend/  # React + Vite
```

`COLCON_IGNORE` keeps this Web workspace out of ROS 2 colcon builds.

## Backend

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

## Frontend

```bash
cd src/idc_web/frontend
npm install
npm run dev -- --host 0.0.0.0
```

The frontend is currently only the React/Vite bootstrap. Application screens and API bindings are added after the DB/API contract is finalized.
