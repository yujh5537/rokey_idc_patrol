import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Robot


router = APIRouter()


def load_robot_poses() -> list[dict]:
    with SessionLocal() as db:
        robots = db.scalars(
            select(Robot).order_by(Robot.id)
        ).all()

        poses = []

        for robot in robots:
            if (
                robot.x is None
                or robot.y is None
                or robot.yaw is None
            ):
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


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            # SQLAlchemy sync DB access가 event loop를 막지 않도록
            # worker thread에서 조회한다.
            poses = await asyncio.to_thread(load_robot_poses)

            server_ts = datetime.now(
                timezone.utc
            ).isoformat()

            # 로봇별 robot_pose 이벤트.
            # 0.5초 주기이므로 각 로봇은 2 Hz.
            for pose in poses:
                await websocket.send_json(
                    {
                        "event": "robot_pose",
                        "data": pose,
                        "server_ts": server_ts,
                    }
                )

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        return
