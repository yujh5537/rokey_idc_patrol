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
from backend.map_api import router as map_router
from backend.ws_api import router as ws_router


# FastAPI 서버가 실행되는 동안 MQTT telemetry를 계속 받아야 하므로
# 서버 전체에서 사용할 MQTT consumer 객체를 하나 만든다.
mqtt_telemetry_consumer = MqttTelemetryConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI가 시작될 때 MQTT consumer를 시작한다.
    mqtt_telemetry_consumer.start()
    try:
        # yield 동안 FastAPI 서버가 정상 동작한다.
        yield
    finally:
        # FastAPI가 종료될 때 MQTT 연결과 background loop도 같이 정리한다.
        mqtt_telemetry_consumer.stop()


# FastAPI 애플리케이션 본체이다.
# uvicorn backend.main:app 명령에서 마지막 app이 바로 이 객체를 뜻한다.
app = FastAPI(
    title="IDC Patrol Control Server",
    version="1.0.0",
    lifespan=lifespan,
)


def check_mqtt_broker() -> None:
    # MQTT broker의 host:port에 TCP 연결이 가능한지 간단히 확인한다.
    # 실제 메시지를 publish/subscribe하는 함수가 아니라 health check 용도이다.
    with socket.create_connection(
        (settings.mqtt_host, settings.mqtt_port),
        timeout=1.0,
    ):
        pass


def robot_to_dict(robot: Robot) -> dict:
    # SQLAlchemy Robot 객체를 API 응답용 Python dict로 바꾼다.
    # DB에는 battery가 0.0~1.0으로 저장되므로 UI용 percent도 같이 만든다.
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
    # Event ORM 객체를 REST API가 JSON으로 반환하기 쉬운 dict 형태로 바꾼다.
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


# 서버, PostgreSQL, MQTT broker가 모두 살아 있는지 확인하는 health API이다.
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
        # PostgreSQL 연결에 문제가 있으면 HTTP 503을 반환한다.
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc

    except OSError as exc:
        # Mosquitto broker에 TCP 연결할 수 없으면 HTTP 503을 반환한다.
        raise HTTPException(
            status_code=503,
            detail="mqtt broker unavailable",
        ) from exc


# 현재 DB에 저장된 모든 로봇의 최신 상태를 반환한다.
# React가 처음 열릴 때 이 API로 battery/state/x/y/yaw 초기값을 가져온다.
@app.get("/api/v1/robots")
def list_robots(db: Session = Depends(get_db)):
    robots = db.scalars(
        select(Robot).order_by(Robot.id)
    ).all()
    return [robot_to_dict(robot) for robot in robots]


# 특정 robot_id 하나만 조회할 때 사용하는 API이다.
@app.get("/api/v1/robots/{robot_id}")
def get_robot(robot_id: str, db: Session = Depends(get_db)):
    robot = db.get(Robot, robot_id)
    if robot is None:
        raise HTTPException(
            status_code=404,
            detail="robot not found",
        )
    return robot_to_dict(robot)


# 이벤트 목록을 조회하는 REST API이다.
# type/status/robot/rack/zone 조건을 query parameter로 선택해서 필터링할 수 있다.
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


# 가장 기본적인 서버 동작 확인용 endpoint이다.
@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }

# 별도 파일에 정의한 map API와 WebSocket API를 이 FastAPI app에 연결한다.
app.include_router(map_router)
app.include_router(ws_router)
