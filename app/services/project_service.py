import asyncio
from datetime import datetime, date
from collections import defaultdict
from app.core.errors import AppError
from app.domain.snapshot import SnapshotCache
from app.repositories.sheets_repository import GoogleSheetsRepository
from app.schemas.project import ProjectCreateRequest, PaymentCreateRequest
from app.schemas.domain import Project, Payment

class ProjectService:
    def __init__(
        self, 
        cache: SnapshotCache, 
        repository: GoogleSheetsRepository, 
        write_lock: asyncio.Lock
    ):
        self.cache = cache
        self.repository = repository
        self.write_lock = write_lock

    async def create_project(self, request: ProjectCreateRequest, username: str) -> dict:
        async with self.write_lock:
            # Re-read cache to ensure latest data
            projects, payments, _ = await self.cache.get_data()
            
            # 1. Cek duplikat id_proyek (BR-06)
            if any(p.id_proyek == request.id_proyek for p in projects):
                raise AppError("INVOICE_DUPLICATE", "Nomor invoice sudah tercatat", 409)

            # 2. Hitung nilai_proyek (BR-01)
            nilai_proyek = request.subtotal - request.diskon
            
            # 3. Validasi DP (BR-03)
            if request.dp > nilai_proyek:
                raise AppError("DP_EXCEEDS_VALUE", "DP melebihi nilai proyek", 422)

            bulan_filter = request.tanggal.strftime("%Y-%m")
            
            # Create Project domain model
            project = Project(
                id_proyek=request.id_proyek,
                tanggal=request.tanggal,
                nama_klien=request.nama_klien,
                alamat=request.alamat,
                pekerjaan=request.pekerjaan,
                subtotal=request.subtotal,
                diskon=request.diskon,
                nilai_proyek=nilai_proyek,
                bulan_filter=bulan_filter,
                dibuat_oleh=username
            )

            # Create DP Payment if dp > 0
            dp_payment = None
            if request.dp > 0:
                # Generate id_bayar (PAY-YYMM-NNN)
                prefix = f"PAY-{request.tanggal.strftime('%y%m')}-"
                
                # Find latest NNN for this month
                max_nnn = 0
                for p in payments:
                    if p.id_bayar.startswith(prefix):
                        try:
                            nnn = int(p.id_bayar.split("-")[-1])
                            if nnn > max_nnn:
                                max_nnn = nnn
                        except ValueError:
                            pass
                
                new_id_bayar = f"{prefix}{max_nnn + 1:03d}"
                
                tipe = "PELUNASAN" if request.dp == nilai_proyek else "DP"
                
                dp_payment = Payment(
                    id_bayar=new_id_bayar,
                    id_proyek=request.id_proyek,
                    tanggal=request.tanggal,
                    nominal=request.dp,
                    tipe=tipe,
                    bulan_filter=bulan_filter,
                    dicatat_oleh=username
                )

            # Write to Sheets (Atomic batch_update)
            await self.repository.write_project_and_dp(project, dp_payment)
            
            # Refresh Cache Synchronously so read-your-writes works
            await self.cache.force_refresh()
            
            return {
                "proyek": project.model_dump(),
                "pembayaran": dp_payment.model_dump() if dp_payment else None
            }

    async def add_payment(self, id_proyek: str, request: PaymentCreateRequest, username: str) -> dict:
        async with self.write_lock:
            projects, payments, _ = await self.cache.get_data()
            
            # Find project
            project = next((p for p in projects if p.id_proyek == id_proyek), None)
            if not project:
                raise AppError("PROJECT_NOT_FOUND", "Proyek tidak ditemukan", 404)
                
            # Calculate total dibayar
            total_dibayar = sum(p.nominal for p in payments if p.id_proyek == id_proyek)
            sisa = max(project.nilai_proyek - total_dibayar, 0)
            
            if sisa <= 0:
                raise AppError("PAYMENT_EXCEEDS_BALANCE", "Proyek sudah lunas", 422)
                
            if request.nominal > sisa:
                raise AppError(
                    "PAYMENT_EXCEEDS_BALANCE",
                    "Nominal melebihi sisa piutang",
                    422,
                    {"sisa": sisa},
                )
                
            if request.nominal <= 0:
                raise AppError("VALIDATION_ERROR", "Nominal harus > 0", 422)
                
            tipe = "PELUNASAN" if request.nominal == sisa else "CICILAN"
            
            # Generate id_bayar
            today = date.today()
            prefix = f"PAY-{today.strftime('%y%m')}-"
            max_nnn = 0
            for p in payments:
                if p.id_bayar.startswith(prefix):
                    try:
                        nnn = int(p.id_bayar.split("-")[-1])
                        if nnn > max_nnn:
                            max_nnn = nnn
                    except ValueError:
                        pass
            
            new_id_bayar = f"{prefix}{max_nnn + 1:03d}"
            bulan_filter = today.strftime("%Y-%m")
            
            payment = Payment(
                id_bayar=new_id_bayar,
                id_proyek=id_proyek,
                tanggal=today,
                nominal=request.nominal,
                tipe=tipe,
                bulan_filter=bulan_filter,
                dicatat_oleh=username
            )
            
            await self.repository.write_payment(payment)
            
            # Refresh cache
            await self.cache.force_refresh()
            
            return {"pembayaran": payment.model_dump()}
