from fastapi import APIRouter, Depends
from app.core.dependencies import get_snapshot_cache
from app.core.security import get_current_admin
from app.domain.snapshot import SnapshotCache
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
    
    # Calculate sisa
    from collections import defaultdict
    payments_by_project = defaultdict(int)
    for p in payments:
        payments_by_project[p.id_proyek] += p.nominal
        
    receivables = []
    for proj in projects:
        total_dibayar = payments_by_project.get(proj.id_proyek, 0)
        sisa = max(proj.nilai_proyek - total_dibayar, 0)
        
        if sisa > 0:
            # calculate days passed
            try:
                # proj.tanggal is a string in YYYY-MM-DD
                tgl = date.fromisoformat(proj.tanggal)
                umur = (date.today() - tgl).days
            except:
                umur = 0
                
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
