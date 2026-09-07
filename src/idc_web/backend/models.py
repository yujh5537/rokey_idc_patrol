from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


# ============================================================
# 1. robots
# ============================================================

class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    last_seen: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    battery: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    state: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    yaw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )


# ============================================================
# 2. patrol_runs
# ============================================================

class PatrolRun(Base):
    __tablename__ = "patrol_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    started_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ended_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    map_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    coverage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )


# ============================================================
# 3. waypoints
# ============================================================

class Waypoint(Base):
    __tablename__ = "waypoints"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("patrol_runs.id"),
        nullable=True,
    )

    robot_id: Mapped[str | None] = mapped_column(
        ForeignKey("robots.id"),
        nullable=True,
    )

    seq: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    yaw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    rack_id: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    visited_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    result: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )


# ============================================================
# 4. zones
# ============================================================

class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(
        String(16),
        primary_key=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    polygon_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    allowed_from: Mapped[object | None] = mapped_column(
        Time,
        nullable=True,
    )

    allowed_to: Mapped[object | None] = mapped_column(
        Time,
        nullable=True,
    )

    min_persons: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    max_dwell_sec: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    allowed_person_ids: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ============================================================
# 5. racks
# ============================================================

class Rack(Base):
    __tablename__ = "racks"

    id: Mapped[str] = mapped_column(
        String(16),
        primary_key=True,
    )

    aruco_id: Mapped[int | None] = mapped_column(
        Integer,
        unique=True,
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    yaw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    zone_id: Mapped[str | None] = mapped_column(
        ForeignKey("zones.id"),
        nullable=True,
    )

    baseline_door: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    baseline_led: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )


# ============================================================
# 6. persons
# ============================================================

class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    org: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    consent_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    embedding: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )

    registered_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# 7. auth_events
# ============================================================

class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"),
        nullable=True,
    )

    door_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ts: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# 8. events
# ============================================================

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("patrol_runs.id"),
        nullable=True,
    )

    type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    severity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    zone_id: Mapped[str | None] = mapped_column(
        ForeignKey("zones.id"),
        nullable=True,
    )

    rack_id: Mapped[str | None] = mapped_column(
        ForeignKey("racks.id"),
        nullable=True,
    )

    robot_id: Mapped[str | None] = mapped_column(
        ForeignKey("robots.id"),
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    first_ts: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_ts: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    acked_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    acked_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    detail_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


# ============================================================
# 9. evidence
# ============================================================

class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"),
        nullable=True,
    )

    robot_id: Mapped[str | None] = mapped_column(
        ForeignKey("robots.id"),
        nullable=True,
    )

    ts: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    path_blurred: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    path_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    yaw: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )


# ============================================================
# 10. audit_log
# ============================================================

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    ts: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actor: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    action: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    target: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    prev_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
