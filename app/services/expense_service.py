import asyncio
from datetime import datetime, date
from fastapi import HTTPException
from app.domain.snapshot import SnapshotCache
from app.repositories.sheets_repository import GoogleSheetsRepository
from app.schemas.domain import Expense
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
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "Nominal harus > 0"})
            
        async with self.write_lock:
            _, _, expenses = await self.cache.get_data()
            
            # Generate id_pengeluaran (OUT-YYMM-NNN)
            prefix = f"OUT-{request.tanggal.strftime('%y%m')}-"
            max_nnn = 0
            for e in expenses:
                if e.id_pengeluaran.startswith(prefix):
                    try:
                        nnn = int(e.id_pengeluaran.split("-")[-1])
                        if nnn > max_nnn:
                            max_nnn = nnn
                    except ValueError:
                        pass
            
            new_id = f"{prefix}{max_nnn + 1:03d}"
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
            
            # Refresh cache
            await self.cache.force_refresh()
            
            return {"pengeluaran": expense.model_dump()}
