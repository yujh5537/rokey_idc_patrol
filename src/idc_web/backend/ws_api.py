import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Robot


# 이 파일은 PostgreSQL에 저장된 로봇 좌표를 읽어서
# 브라우저(React)로 실시간 전송하는 WebSocket API를 담당한다.
# 데이터 흐름:
# MQTT -> mqtt_consumer.py -> PostgreSQL -> ws_api.py -> React
router = APIRouter()


def load_robot_poses() -> list[dict]:
    # SessionLocal()은 PostgreSQL과 대화하기 위한 SQLAlchemy 세션이다.
    # robots 테이블에서 현재 저장된 모든 로봇 정보를 읽는다.
    with SessionLocal() as db:
        robots = db.scalars(
            select(Robot).order_by(Robot.id)
        ).all()

        poses = []

        for robot in robots:
            # 좌표 셋(x, y, yaw)이 모두 있어야 지도에 실제 위치를 찍을 수 있다.
            # 아직 pose를 받은 적 없는 로봇은 WebSocket pose 전송 대상에서 제외한다.
            if (
                robot.x is None
                or robot.y is None
                or robot.yaw is None
            ):
                continue

            # ORM 객체를 브라우저가 받기 쉬운 JSON 형태의 dict로 변환한다.
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


# React에서는 ws://<host>/api/v1/ws 주소로 이 endpoint에 연결한다.
@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    # WebSocket 연결 요청을 수락해야 서버와 브라우저가 양방향 연결 상태가 된다.
    await websocket.accept()

    try:
        while True:
            # SQLAlchemy sync DB access가 event loop를 막지 않도록
            # worker thread에서 조회한다.
            poses = await asyncio.to_thread(load_robot_poses)

            # 서버가 이번 데이터를 보낸 시각이다.
            # UTC 기준 ISO-8601 문자열로 보내므로 로그 비교가 쉽다.
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

            # 0.5초 대기 후 다시 DB를 읽는다. 즉 초당 2번(2 Hz) 갱신한다.
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        # 사용자가 브라우저를 닫거나 새로고침하면 연결이 끊길 수 있다.
        # 정상적인 연결 종료이므로 별도 에러로 처리하지 않고 함수만 종료한다.
        return
