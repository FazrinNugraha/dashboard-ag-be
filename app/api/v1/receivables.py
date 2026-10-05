from fastapi import APIRouter, Depends
from app.core.dependencies import get_snapshot_cache
from app.core.security import get_current_admin
from app.domain.snapshot import SnapshotCache
from app.domain.metrics import compute_receivables
from datetime import date

router = APIRouter(
    prefix="/receivables",
    tags=["Receivables"],
    dependencies=[Depends(get_current_admin)],
)

@router.get("")
async def get_receivables(
    cache: SnapshotCache = Depends(get_snapshot_cache)
):
    projects, payments, _ = await cache.get_data()

    today = date.today()
    receivables = []
    for proj, total_dibayar, sisa in compute_receivables(projects, payments):
        umur = (today - proj.tanggal).days
        proj_dict = proj.model_dump()
        proj_dict["sisa_piutang"] = sisa
        proj_dict["total_dibayar"] = total_dibayar
        proj_dict["umur_hari"] = umur
        receivables.append(proj_dict)

    # Sort by oldest first
    receivables.sort(key=lambda x: x["umur_hari"], reverse=True)

    return {
        "data": receivables,
        "total_piutang": sum(r["sisa_piutang"] for r in receivables),
        "jumlah_klien": len(receivables)
    }
