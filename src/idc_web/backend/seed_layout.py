from __future__ import annotations

from pathlib import Path

import yaml

from backend.database import SessionLocal
from backend.models import Rack, Zone


REPO_ROOT = Path(__file__).resolve().parents[3]
LAYOUT_PATH = REPO_ROOT / "src" / "idc_bringup" / "config" / "racks.yaml"


def _finite(value: object, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid {field} in {LAYOUT_PATH}") from exc

    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise RuntimeError(f"non-finite {field} in {LAYOUT_PATH}")
    return parsed


def seed_static_layout() -> None:
    """Synchronize MAP-02 zone/rack identity and coordinates into PostgreSQL.

    The source of truth is idc_bringup/config/racks.yaml. Only static identity
    and position fields are synchronized; runtime/baseline state is preserved.
    """

    if not LAYOUT_PATH.is_file():
        raise RuntimeError(f"MAP-02 layout not found: {LAYOUT_PATH}")

    with LAYOUT_PATH.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)

    if not isinstance(data, dict):
        raise RuntimeError("MAP-02 racks.yaml must contain a mapping")

    zones = data.get("zones")
    racks = data.get("racks")
    if not isinstance(zones, dict) or set(zones) != {"Z1", "Z2", "Z3", "Z4"}:
        raise RuntimeError("MAP-02 must define exactly Z1..Z4")
    if not isinstance(racks, list) or len(racks) != 56:
        raise RuntimeError("MAP-02 must define exactly 56 racks")

    seen_ids: set[str] = set()
    seen_aruco: set[int] = set()

    with SessionLocal() as db:
        for zone_id in ("Z1", "Z2", "Z3", "Z4"):
            if db.get(Zone, zone_id) is None:
                db.add(Zone(id=zone_id))
        db.flush()

        for row in racks:
            if not isinstance(row, dict):
                raise RuntimeError("invalid rack row in MAP-02 racks.yaml")

            rack_id = row.get("rack_id")
            zone_id = row.get("zone_id")
            aruco_id = row.get("aruco_id")

            if not isinstance(rack_id, str) or rack_id not in {
                f"R{index:02d}" for index in range(1, 57)
            }:
                raise RuntimeError(f"invalid rack_id: {rack_id!r}")
            if rack_id in seen_ids:
                raise RuntimeError(f"duplicate rack_id: {rack_id}")
            if zone_id not in zones:
                raise RuntimeError(f"invalid zone_id for {rack_id}: {zone_id!r}")
            if not isinstance(aruco_id, int) or not 1 <= aruco_id <= 56:
                raise RuntimeError(f"invalid aruco_id for {rack_id}: {aruco_id!r}")
            if aruco_id in seen_aruco:
                raise RuntimeError(f"duplicate aruco_id: {aruco_id}")

            seen_ids.add(rack_id)
            seen_aruco.add(aruco_id)

            rack = db.get(Rack, rack_id)
            if rack is None:
                rack = Rack(id=rack_id)
                db.add(rack)

            rack.aruco_id = aruco_id
            rack.x = _finite(row.get("x"), f"{rack_id}.x")
            rack.y = _finite(row.get("y"), f"{rack_id}.y")
            # Current MAP-02 exposes rack face and inspect_pose yaw, but no
            # top-level rack yaw. Do not invent a rack yaw value here.
            rack.zone_id = zone_id

        db.commit()
