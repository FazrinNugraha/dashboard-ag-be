from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_snapshot_cache, get_repository, get_write_lock
from app.domain.snapshot import SnapshotCache
from app.services.expense_service import ExpenseService, ExpenseCreateRequest
from app.core.security import get_current_admin
import asyncio

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.get("")
async def get_expenses(
    month: str = Query(None, description="Filter by YYYY-MM"),
    page: int = 1,
    page_size: int = 20,
    cache: SnapshotCache = Depends(get_snapshot_cache)
):
    _, _, expenses = await cache.get_data()
    
    # Filter
    filtered = expenses
    if month:
        filtered = [e for e in filtered if e.bulan_filter == month]
        
    # Sort descending by date
    filtered.sort(key=lambda x: x.tanggal, reverse=True)
    
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "data": filtered[start:end],
        "total": len(filtered),
        "page": page,
        "page_size": page_size
    }

@router.post("", status_code=201)
async def create_expense(
    request: ExpenseCreateRequest,
    cache: SnapshotCache = Depends(get_snapshot_cache),
    repo = Depends(get_repository),
    lock: asyncio.Lock = Depends(get_write_lock),
    username: str = Depends(get_current_admin)
):
    service = ExpenseService(cache, repo, lock)
    return await service.create_expense(request, username)
