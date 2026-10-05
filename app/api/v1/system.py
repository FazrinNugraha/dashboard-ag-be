from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import get_settings
from app.core.dependencies import get_snapshot_cache
from app.core.security import get_current_admin
from app.domain.snapshot import SnapshotCache

router = APIRouter(tags=["System"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check (publik)."""
    return {"status": "ok", "version": __version__, "env": get_settings().ENV}


@router.get("/health/sheets", dependencies=[Depends(get_current_admin)])
async def health_sheets(cache: SnapshotCache = Depends(get_snapshot_cache)) -> dict:
    """Status snapshot data dari Google Sheets, termasuk baris yang dilewati."""
    stats = cache.stats()
    total_skipped = sum(r.get("skipped", 0) for r in stats["rows"].values())
    return {
        "status": "degraded" if total_skipped else "ok",
        **stats,
        "skipped_total": total_skipped,
    }


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_data(cache: SnapshotCache = Depends(get_snapshot_cache)):
    """Force refresh the snapshot cache from Google Sheets."""
    await cache.force_refresh()
    return {"status": "ok", "message": "Snapshot cache refreshed."}
