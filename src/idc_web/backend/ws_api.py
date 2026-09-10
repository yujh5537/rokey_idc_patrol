import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Event, Robot


# PostgreSQL -> browser realtime path.
# MQTT -> mqtt_consumer.py -> PostgreSQL -> ws_api.py -> React
router = APIRouter()


def load_robot_poses() -> list[dict]:
    with SessionLocal() as db:
        robots = db.scalars(select(Robot).order_by(Robot.id)).all()
        poses = []

        for robot in robots:
            if robot.x is None or robot.y is None or robot.yaw is None:
                continue

            poses.append(
                {
                    "robot_id": robot.id,
                    "x": robot.x,
                    "y": robot.y,
                    "yaw": robot.yaw,
                    "last_seen": (
                        robot.last_seen.isoformat()
                        if robot.last_seen is not None
                        else None
                    ),
                }
            )

        return poses


def load_events_after(event_id: int) -> list[dict]:
    with SessionLocal() as db:
        events = db.scalars(
            select(Event)
            .where(Event.id > event_id)
            .order_by(Event.id.asc())
            .limit(100)
        ).all()

        return [
            {
                "event_id": event.id,
                "type": event.type,
                "severity": event.severity,
                "zone_id": event.zone_id,
                "rack_id": event.rack_id,
                "robot_id": event.robot_id,
                "x": event.x,
                "y": event.y,
                "first_ts": (
                    event.first_ts.isoformat()
                    if event.first_ts is not None
                    else None
                ),
                "last_ts": (
                    event.last_ts.isoformat()
                    if event.last_ts is not None
                    else None
                ),
                "status": event.status,
                "detail_json": event.detail_json,
            }
            for event in events
        ]


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    raw_after = websocket.query_params.get("after_event_id", "0")
    try:
        last_event_id = max(0, int(raw_after))
    except ValueError:
        last_event_id = 0

    try:
        while True:
            poses, new_events = await asyncio.gather(
                asyncio.to_thread(load_robot_poses),
                asyncio.to_thread(load_events_after, last_event_id),
            )

            server_ts = datetime.now(timezone.utc).isoformat()

            for pose in poses:
                await websocket.send_json(
                    {
                        "event": "robot_pose",
                        "data": pose,
                        "server_ts": server_ts,
                    }
                )

            for event in new_events:
                await websocket.send_json(
                    {
                        "event": "event_new",
                        "data": event,
                        "server_ts": server_ts,
                    }
                )
                last_event_id = max(last_event_id, int(event["event_id"]))

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        return
