from __future__ import annotations

import csv
import math
from pathlib import Path

from sqlalchemy import text

from backend.database import engine


TESTBED_LENGTH_MM = 5700.0
RACK_THICKNESS_MM = 85.0
R08_R49_LEFT_SHIFT_MM = RACK_THICKNESS_MM * 3.0
CSV_PATH = Path(__file__).resolve().parent / "data" / "rack_coords_generalized.csv"


def _load_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[int] = set()

    with CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {
            "rack_id",
            "x_mm",
            "y_mm",
            "yaw_deg",
            "pixel_x_frac",
            "pixel_y_frac",
            "screen_rotate_deg",
        }
        if set(reader.fieldnames or []) != expected:
            raise RuntimeError("rack coordinate CSV header does not match the seed contract")

        for raw in reader:
            aruco_id = int(raw["rack_id"])
            if aruco_id < 1 or aruco_id > 56 or aruco_id in seen:
                raise RuntimeError(f"invalid or duplicate rack_id: {aruco_id}")
            seen.add(aruco_id)

            x_mm = float(raw["x_mm"])
            y_mm = float(raw["y_mm"])
            yaw_deg = float(raw["yaw_deg"])
            base_screen_x = float(raw["pixel_x_frac"])
            base_screen_y = float(raw["pixel_y_frac"])
            screen_rotate_deg = float(raw["screen_rotate_deg"])

            # UI layout is now frozen to the verified control-screen placement:
            # 1) portrait map -> 90deg left landscape view
            # 2) rack layer top/bottom flip
            # 3) R08..R49 shifted left by 3 rack-thickness cells (255 mm)
            left_shift_frac = (
                R08_R49_LEFT_SHIFT_MM / TESTBED_LENGTH_MM
                if 8 <= aruco_id <= 49
                else 0.0
            )
            screen_x_frac = base_screen_x - left_shift_frac
            screen_y_frac = 1.0 - base_screen_y

            if not (0.0 <= screen_x_frac <= 1.0 and 0.0 <= screen_y_frac <= 1.0):
                raise RuntimeError(f"rack {aruco_id} final screen position is outside 0..1")

            rows.append(
                {
                    "id": f"R{aruco_id:02d}",
                    "aruco_id": aruco_id,
                    # Keep physical/mechanical coordinates as the DB source-of-truth.
                    "x": x_mm / 1000.0,
                    "y": y_mm / 1000.0,
                    "yaw": math.radians(yaw_deg),
                    # Store the frozen web overlay separately from physical x/y/yaw.
                    "screen_x_frac": screen_x_frac,
                    "screen_y_frac": screen_y_frac,
                    "screen_rotate_deg": screen_rotate_deg,
                }
            )

    if len(rows) != 56:
        raise RuntimeError(f"expected 56 racks, received {len(rows)}")
    return rows


def seed_racks() -> None:
    rows = _load_rows()

    with engine.begin() as connection:
        # Existing PC4 databases were created before the web-overlay fields existed.
        # ADD COLUMN IF NOT EXISTS keeps this migration idempotent.
        connection.execute(
            text(
                """
                ALTER TABLE racks
                    ADD COLUMN IF NOT EXISTS screen_x_frac DOUBLE PRECISION,
                    ADD COLUMN IF NOT EXISTS screen_y_frac DOUBLE PRECISION,
                    ADD COLUMN IF NOT EXISTS screen_rotate_deg DOUBLE PRECISION
                """
            )
        )

        statement = text(
            """
            INSERT INTO racks (
                id,
                aruco_id,
                x,
                y,
                yaw,
                zone_id,
                baseline_door,
                baseline_led,
                screen_x_frac,
                screen_y_frac,
                screen_rotate_deg
            ) VALUES (
                :id,
                :aruco_id,
                :x,
                :y,
                :yaw,
                NULL,
                NULL,
                NULL,
                :screen_x_frac,
                :screen_y_frac,
                :screen_rotate_deg
            )
            ON CONFLICT (id) DO UPDATE SET
                aruco_id = EXCLUDED.aruco_id,
                x = EXCLUDED.x,
                y = EXCLUDED.y,
                yaw = EXCLUDED.yaw,
                screen_x_frac = EXCLUDED.screen_x_frac,
                screen_y_frac = EXCLUDED.screen_y_frac,
                screen_rotate_deg = EXCLUDED.screen_rotate_deg
            """
        )
        connection.execute(statement, rows)

        count = connection.execute(text("SELECT COUNT(*) FROM racks")).scalar_one()

    print(f"rack seed complete: {count} rack rows in database")
    print("expected canonical rack IDs: R01..R56")
    print("R08..R49 web overlay: shifted left 255 mm; rack layer vertically flipped")


if __name__ == "__main__":
    seed_racks()
