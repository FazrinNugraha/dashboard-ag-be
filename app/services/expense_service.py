import asyncio
from datetime import date
from app.core.errors import AppError
from app.domain.snapshot import SnapshotCache
from app.repositories.sheets_repository import GoogleSheetsRepository
from app.schemas.domain import Expense
from app.services.ids import next_sequential_id
from pydantic import BaseModel
from typing import Literal

class ExpenseCreateRequest(BaseModel):
    tanggal: date
    kategori: Literal["BAHAN_BAKU", "AKSESORIS", "UPAH", "OPERASIONAL", "LAINNYA"]
    keterangan: str
    nominal: int

class ExpenseService:
    def __init__(
        self, 
        cache: SnapshotCache, 
        repository: GoogleSheetsRepository, 
        write_lock: asyncio.Lock
    ):
        self.cache = cache
        self.repository = repository
        self.write_lock = write_lock

    async def create_expense(self, request: ExpenseCreateRequest, username: str) -> dict:
        if request.nominal <= 0:
            raise AppError("VALIDATION_ERROR", "Nominal harus > 0", 422)
            
        async with self.write_lock:
            # Pastikan snapshot segar agar ID tidak dihitung dari data basi.
            await self.cache.force_refresh()
            _, _, expenses = await self.cache.get_data()
            
            # Generate id_pengeluaran (OUT-YYMM-NNN) yang dijamin belum terpakai
            prefix = f"OUT-{request.tanggal.strftime('%y%m')}-"
            new_id = next_sequential_id(prefix, {e.id_pengeluaran for e in expenses})
            bulan_filter = request.tanggal.strftime("%Y-%m")
            
            expense = Expense(
                id_pengeluaran=new_id,
                tanggal=request.tanggal,
                kategori=request.kategori,
                keterangan=request.keterangan,
                nominal=request.nominal,
                bulan_filter=bulan_filter,
                dibuat_oleh=username
            )
            
            await self.repository.write_expense(expense)
            
            # Update cache inkremental (read-your-writes)
            await self.cache.append_expense(expense)
            
            return {"pengeluaran": expense.model_dump()}
