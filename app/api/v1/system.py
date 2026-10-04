from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["System"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check (publik)."""
    return {"status": "ok", "version": __version__, "env": get_settings().ENV}

from app.core.dependencies import get_snapshot_cache
from app.domain.snapshot import SnapshotCache
from fastapi import Depends

@router.post("/sync")
async def sync_data(cache: SnapshotCache = Depends(get_snapshot_cache)):
    """Force refresh the snapshot cache from Google Sheets."""
    await cache.force_refresh()
    return {"status": "ok", "message": "Snapshot cache refreshed."}
