from contextlib import asynccontextmanager
import socket

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import check_database_connection, get_db
from backend.models import Event, Robot
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


def event_to_dict(event: Event) -> dict:
    return {
        "event_id": event.id,
        "run_id": event.run_id,
        "type": event.type,
        "severity": event.severity,
        "zone_id": event.zone_id,
        "rack_id": event.rack_id,
        "robot_id": event.robot_id,
        "x": event.x,
        "y": event.y,
        "first_ts": event.first_ts,
        "last_ts": event.last_ts,
        "status": event.status,
        "acked_by": event.acked_by,
        "acked_at": event.acked_at,
        "detail_json": event.detail_json,
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


@app.get("/api/v1/events")
def list_events(
    event_type: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    robot_id: str | None = None,
    rack_id: str | None = None,
    zone_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    statement = select(Event)

    if event_type is not None:
        statement = statement.where(Event.type == event_type)
    if status is not None:
        statement = statement.where(Event.status == status)
    if robot_id is not None:
        statement = statement.where(Event.robot_id == robot_id)
    if rack_id is not None:
        statement = statement.where(Event.rack_id == rack_id)
    if zone_id is not None:
        statement = statement.where(Event.zone_id == zone_id)

    events = db.scalars(
        statement.order_by(
            Event.last_ts.desc().nullslast(),
            Event.first_ts.desc().nullslast(),
            Event.id.desc(),
        ).limit(limit)
    ).all()

    return [event_to_dict(event) for event in events]


@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }
