from contextlib import asynccontextmanager
import socket

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import check_database_connection, get_db
from backend.models import Robot
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


@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }
