from contextlib import asynccontextmanager
import socket

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import check_database_connection, get_db
from backend.models import Event, Rack, Robot
from backend.mqtt_consumer import MqttTelemetryConsumer


mqtt_telemetry_consumer = MqttTelemetryConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_telemetry_consumer.start()
    try:
        yield
    finally:
        mqtt_telemetry_consumer.stop()


app = FastAPI(
    title="IDC Patrol Control Server",
    version="1.0.0",
    lifespan=lifespan,
)

# PC4 Vite dev server -> PC4 FastAPI. Production reverse proxy can remove this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.107.124:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


def check_mqtt_broker() -> None:
    with socket.create_connection(
        (settings.mqtt_host, settings.mqtt_port),
        timeout=1.0,
    ):
        pass


def robot_to_dict(robot: Robot) -> dict:
    battery_percent = None
    if robot.battery is not None:
        battery_percent = round(robot.battery * 100.0, 1)

    return {
        "robot_id": robot.id,
        "name": robot.name,
        "last_seen": robot.last_seen,
        "battery": robot.battery,
        "battery_percent": battery_percent,
        "state": robot.state,
        "x": robot.x,
        "y": robot.y,
        "yaw": robot.yaw,
    }


def latest_active_rack_events(db: Session) -> dict[str, Event]:
    resolved_statuses = {"RESOLVED", "CLOSED", "CLEARED"}
    events = db.scalars(
        select(Event)
        .where(Event.rack_id.is_not(None))
        .where(Event.type.in_(["E5", "E7"]))
        .order_by(
            Event.last_ts.desc().nullslast(),
            Event.first_ts.desc().nullslast(),
            Event.id.desc(),
        )
    ).all()

    latest: dict[str, Event] = {}
    seen_racks: set[str] = set()
    for event in events:
        rack_id = event.rack_id
        if rack_id is None or rack_id in seen_racks:
            continue

        # Only the latest rack event decides current state. If the latest event
        # is resolved, an older abnormal event must not become active again.
        seen_racks.add(rack_id)
        status = (event.status or "").upper()
        if status in resolved_statuses:
            continue
        latest[rack_id] = event
    return latest


def rack_to_dict(rack: Rack, event: Event | None = None) -> dict:
    state = "NORMAL"
    if event is not None:
        if event.type == "E5":
            state = "DOOR_OPEN"
        elif event.type == "E7":
            state = "LED_RED"

    return {
        "rack_id": rack.id,
        "aruco_id": rack.aruco_id,
        "x": rack.x,
        "y": rack.y,
        "yaw": rack.yaw,
        "zone_id": rack.zone_id,
        "state": state,
        "severity": event.severity if event is not None else None,
        "updated_at": (
            (event.last_ts or event.first_ts)
            if event is not None
            else None
        ),
    }


@app.get("/api/v1/health")
def health():
    try:
        database = check_database_connection()
        check_mqtt_broker()

        return {
            "status": "ok",
            "service": "idc_server",
            "database": "ok",
            "broker": "ok",
            "database_name": database["database"],
        }

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc

    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="mqtt broker unavailable",
        ) from exc


@app.get("/api/v1/robots")
def list_robots(db: Session = Depends(get_db)):
    robots = db.scalars(
        select(Robot).order_by(Robot.id)
    ).all()
    return [robot_to_dict(robot) for robot in robots]


@app.get("/api/v1/robots/{robot_id}")
def get_robot(robot_id: str, db: Session = Depends(get_db)):
    robot = db.get(Robot, robot_id)
    if robot is None:
        raise HTTPException(
            status_code=404,
            detail="robot not found",
        )
    return robot_to_dict(robot)


@app.get("/api/v1/racks")
def list_racks(db: Session = Depends(get_db)):
    racks = db.scalars(
        select(Rack).order_by(Rack.id)
    ).all()
    events = latest_active_rack_events(db)
    return [
        rack_to_dict(rack, events.get(rack.id))
        for rack in racks
    ]


@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }
