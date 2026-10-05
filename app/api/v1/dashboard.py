from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_snapshot_cache
from app.core.security import get_current_admin
from app.domain.snapshot import SnapshotCache
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_admin)],
)

@router.get("")
async def get_dashboard(
    month: str = Query(..., description="Bulan filter dengan format YYYY-MM"),
    cache: SnapshotCache = Depends(get_snapshot_cache)
):
    service = DashboardService(cache)
    return await service.get_dashboard_summary(month)
