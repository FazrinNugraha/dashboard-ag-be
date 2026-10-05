import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple, List
from app.core.clock import now_local
from app.schemas.domain import Project, Payment, Expense
from app.repositories.sheets_repository import SheetsRepositoryProtocol

logger = logging.getLogger(__name__)

class SnapshotCache:
    def __init__(self, repository: SheetsRepositoryProtocol, ttl_seconds: int = 30):
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self._cache: Optional[Tuple[List[Project], List[Payment], List[Expense]]] = None
        self._last_loaded_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._refreshing = False

    async def get_data(self) -> Tuple[List[Project], List[Payment], List[Expense]]:
        now = now_local()
        
        # If no cache at all, we must wait and fetch synchronously
        if self._cache is None or self._last_loaded_at is None:
            async with self._lock:
                if self._cache is None: # double check
                    await self._refresh_cache_unlocked()
            return self._cache
        
        # Stale-while-revalidate logic
        age = (now - self._last_loaded_at).total_seconds()
        if age > self.ttl_seconds:
            # Trigger background refresh if not already refreshing
            if not self._refreshing:
                asyncio.create_task(self._refresh_cache_background())
                
        return self._cache

    async def force_refresh(self) -> None:
        async with self._lock:
            await self._refresh_cache_unlocked()

    def stats(self) -> dict:
        """Ringkasan keadaan snapshot untuk health check."""
        if self._cache is None:
            return {
                "loaded": False,
                "loaded_at": None,
                "age_seconds": None,
                "counts": {"projects": 0, "payments": 0, "expenses": 0},
                "rows": {},
            }
        projects, payments, expenses = self._cache
        age = None
        if self._last_loaded_at is not None:
            age = round((now_local() - self._last_loaded_at).total_seconds(), 1)
        rows = {}
        if hasattr(self.repository, "last_read_stats"):
            rows = self.repository.last_read_stats()
        return {
            "loaded": True,
            "loaded_at": self._last_loaded_at.isoformat() if self._last_loaded_at else None,
            "age_seconds": age,
            "counts": {
                "projects": len(projects),
                "payments": len(payments),
                "expenses": len(expenses),
            },
            "rows": rows,
        }

    async def append_project(self, project: Project, payment: Optional[Payment] = None) -> None:
        """Tambahkan proyek (dan opsional DP/PELUNASAN) ke snapshot tanpa membaca ulang Sheets.

        Dipanggil setelah penulisan sukses agar read-your-writes tetap berlaku.
        Bila cache belum pernah diisi, lakukan refresh penuh sekali.

        PENTING: hitung total_dibayar / sisa_piutang / status_bayar dari payment
        yang ikut diappend, agar cache langsung mencerminkan status yang benar
        (bukan default "DP" dari constructor Project).
        """
        async with self._lock:
            if self._cache is None:
                await self._refresh_cache_unlocked()
                return
            projects, payments, expenses = self._cache

            # Hitung ulang field kalkulasi berdasarkan payment yang baru disertakan
            total_dibayar = payment.nominal if payment is not None else 0
            sisa_piutang = max(project.nilai_proyek - total_dibayar, 0)
            status_bayar = "LUNAS" if sisa_piutang <= 0 else "DP"

            # Buat salinan project dengan field kalkulasi yang benar
            updated_project = project.model_copy(update={
                "total_dibayar": total_dibayar,
                "sisa_piutang": sisa_piutang,
                "status_bayar": status_bayar,
            })

            self._cache = (
                projects + [updated_project],
                payments + ([payment] if payment is not None else []),
                expenses,
            )
            self._last_loaded_at = now_local()

    async def append_payment(self, payment: Payment) -> None:
        """Tambahkan satu pembayaran ke snapshot tanpa membaca ulang Sheets."""
        async with self._lock:
            if self._cache is None:
                await self._refresh_cache_unlocked()
                return
            projects, payments, expenses = self._cache
            self._cache = (projects, payments + [payment], expenses)
            self._last_loaded_at = now_local()

    async def append_expense(self, expense: Expense) -> None:
        """Tambahkan satu pengeluaran ke snapshot tanpa membaca ulang Sheets."""
        async with self._lock:
            if self._cache is None:
                await self._refresh_cache_unlocked()
                return
            projects, payments, expenses = self._cache
            self._cache = (projects, payments, expenses + [expense])
            self._last_loaded_at = now_local()

    async def _refresh_cache_background(self):
        # Single-flight check
        if self._refreshing:
            return
        
        self._refreshing = True
        try:
            logger.info("Background refreshing snapshot from Google Sheets...")
            async with self._lock:
                await self._refresh_cache_unlocked()
        except Exception as e:
            logger.error(f"Background refresh failed: {e}")
        finally:
            self._refreshing = False

    async def _refresh_cache_unlocked(self):
        try:
            projects, payments, expenses = await self.repository.read_all()
            self._cache = (projects, payments, expenses)
            self._last_loaded_at = now_local()
            logger.info(f"Snapshot refreshed. {len(projects)} projects, {len(payments)} payments, {len(expenses)} expenses.")
        except Exception as e:
            logger.error(f"Failed to refresh cache: {e}")
            raise e
