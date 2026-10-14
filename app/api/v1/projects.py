from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_snapshot_cache, get_repository, get_write_lock
from app.domain.snapshot import SnapshotCache
from app.services.project_service import ProjectService
from app.domain.metrics import total_expense_by_project, project_profit
from app.schemas.project import ProjectCreateRequest, PaymentCreateRequest
from app.core.security import get_current_admin
import asyncio

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.get("", dependencies=[Depends(get_current_admin)])
async def get_projects(
    month: str = Query(None, description="Filter by YYYY-MM"),
    q: str = Query(None, description="Search by client name"),
    page: int = Query(1, ge=1),
    # Maks 500 per permintaan: cukup untuk daftar lengkap proyek (dropdown & tabel).
    page_size: int = Query(20, ge=1, le=500),
    cache: SnapshotCache = Depends(get_snapshot_cache)
):
    projects, _, expenses = await cache.get_data()
    
    # Filter
    filtered = projects
    if month:
        filtered = [p for p in filtered if p.bulan_filter == month]
    if q:
        filtered = [p for p in filtered if q.lower() in p.nama_klien.lower()]
        
    # Sort by tanggal descending (latest first). sorted() agar cache tidak ikut berubah.
    filtered = sorted(filtered, key=lambda x: x.tanggal, reverse=True)
    
    # Paginate
    start = (page - 1) * page_size
    end = start + page_size

    # Gabungkan data proyek dengan pengeluaran & laba per proyek
    expense_by_project = total_expense_by_project(expenses)
    data = [
        {**p.model_dump(), **project_profit(p.nilai_proyek, expense_by_project.get(p.id_proyek, 0))}
        for p in filtered[start:end]
    ]
    
    return {
        "data": data,
        "total": len(filtered),
        "page": page,
        "page_size": page_size
    }

@router.post("", status_code=201)
async def create_project(
    request: ProjectCreateRequest,
    cache: SnapshotCache = Depends(get_snapshot_cache),
    repo = Depends(get_repository),
    lock: asyncio.Lock = Depends(get_write_lock),
    username: str = Depends(get_current_admin)
):
    service = ProjectService(cache, repo, lock)
    return await service.create_project(request, username)

@router.post("/{id_proyek}/payments", status_code=201)
async def add_payment(
    id_proyek: str,
    request: PaymentCreateRequest,
    cache: SnapshotCache = Depends(get_snapshot_cache),
    repo = Depends(get_repository),
    lock: asyncio.Lock = Depends(get_write_lock),
    username: str = Depends(get_current_admin)
):
    service = ProjectService(cache, repo, lock)
    return await service.add_payment(id_proyek, request, username)
