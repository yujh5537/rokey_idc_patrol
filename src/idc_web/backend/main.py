import socket

from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from backend.config import settings
from backend.database import check_database_connection


app = FastAPI(
    title="IDC Patrol Control Server",
    version="1.0.0",
)


def check_mqtt_broker() -> None:
    with socket.create_connection(
        (settings.mqtt_host, settings.mqtt_port),
        timeout=1.0,
    ):
        pass


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


@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }
