from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter(
    prefix="/api/v1/map",
    tags=["map"],
)

# repo/src/idc_web/backend/map_api.py
#               ↑ parents[3] = repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

MAP_DIR = REPO_ROOT / "maps" / "current"
MAP_YAML = MAP_DIR / "merged.yaml"
MAP_PGM = MAP_DIR / "merged.pgm"


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"current map file not found: {path.name}",
        )
    return path


@router.get("")
def get_current_map():
    """
    Return metadata and URLs for the current merged SLAM map.

    Actual map files are transferred from PC3 to PC4 by SSH/rsync.
    """
    yaml_path = require_file(MAP_YAML)
    pgm_path = require_file(MAP_PGM)

    updated_timestamp = max(
        yaml_path.stat().st_mtime,
        pgm_path.stat().st_mtime,
    )

    updated_at = datetime.fromtimestamp(
        updated_timestamp,
        tz=timezone.utc,
    ).isoformat()

    return {
        "map_id": "current",
        "yaml_file": yaml_path.name,
        "image_file": pgm_path.name,
        "yaml_url": "/api/v1/map/yaml",
        "image_url": "/api/v1/map/image",
        "updated_at": updated_at,
    }


@router.get("/yaml")
def get_current_map_yaml():
    path = require_file(MAP_YAML)

    return FileResponse(
        path=path,
        media_type="text/yaml",
        filename="merged.yaml",
    )


@router.get("/image")
def get_current_map_image():
    path = require_file(MAP_PGM)

    return FileResponse(
        path=path,
        media_type="image/x-portable-graymap",
        filename="merged.pgm",
    )
