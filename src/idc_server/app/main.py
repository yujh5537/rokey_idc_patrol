from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database_connection


app = FastAPI(
    title="IDC Patrol Control Server",
    version="1.0.0",
)


@app.get("/health")
def health():
    try:
        check_database_connection()

        return {
            "status": "ok",
            "service": "idc_server",
            "database": "ok",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        )


@app.get("/")
def root():
    return {
        "service": "idc_server",
        "status": "running",
    }
