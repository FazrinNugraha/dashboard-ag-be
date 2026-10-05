"""Test logika service dengan repository in-memory (tanpa Google Sheets).

Menjalankan coroutine via asyncio.run agar tidak menambah dependensi pytest-asyncio.
"""
import asyncio
from datetime import date

import pytest

from app.core.errors import AppError
from app.domain.snapshot import SnapshotCache
from app.schemas.domain import Project, Payment, Expense
from app.schemas.project import ProjectCreateRequest, PaymentCreateRequest
from app.services.expense_service import ExpenseCreateRequest, ExpenseService
from app.services.ids import next_sequential_id
from app.services.project_service import ProjectService


class InMemoryRepository:
    def __init__(self, projects=None, payments=None, expenses=None):
        self.projects = list(projects or [])
        self.payments = list(payments or [])
        self.expenses = list(expenses or [])

    async def read_all(self):
        return list(self.projects), list(self.payments), list(self.expenses)

    async def write_project_and_dp(self, project, dp_payment):
        self.projects.append(project)
        if dp_payment:
            self.payments.append(dp_payment)

    async def write_payment(self, payment):
        self.payments.append(payment)

    async def write_expense(self, expense):
        self.expenses.append(expense)


def make_cache(repo):
    cache = SnapshotCache(repo, ttl_seconds=30)
    asyncio.run(cache.force_refresh())
    return cache


def make_project(id_proyek, nilai=1000, bulan="2026-10"):
    return Project(
        id_proyek=id_proyek,
        tanggal=date(2026, 10, 1),
        nama_klien="K",
        alamat="A",
        pekerjaan="P",
        subtotal=nilai,
        diskon=0,
        nilai_proyek=nilai,
        bulan_filter=bulan,
        dibuat_oleh="admin1",
    )


class TestNextSequentialId:
    def test_lanjut_dari_numerik_terbesar(self):
        assert next_sequential_id("PAY-2610-", {"PAY-2610-001", "PAY-2610-005"}) == "PAY-2610-006"

    def test_abaikan_suffix_non_numerik(self):
        ids = {"PAY-2609-001", "PAY-2609-9B"}
        assert next_sequential_id("PAY-2609-", ids) == "PAY-2609-002"

    def test_prefix_bulan_lain_mulai_satu(self):
        assert next_sequential_id("PAY-2611-", {"PAY-2610-005"}) == "PAY-2611-001"

    def test_tidak_menghasilkan_id_yang_sudah_ada(self):
        ids = {"OUT-2610-001", "OUT-2610-002", "OUT-2610-003"}
        assert next_sequential_id("OUT-2610-", ids) == "OUT-2610-004"


class TestCreateProject:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_hitung_nilai_dan_tulis_dp(self):
        repo = InMemoryRepository()
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        req = ProjectCreateRequest(
            id_proyek="INV-2610-001", tanggal=date(2026, 10, 3), nama_klien="BPK",
            alamat="A", pekerjaan="P", subtotal=21_700_000, diskon=700_000, dp=10_000_000,
        )
        result = self._run(service.create_project(req, "admin1"))
        assert result["proyek"]["nilai_proyek"] == 21_000_000
        assert result["pembayaran"]["nominal"] == 10_000_000
        assert result["pembayaran"]["tipe"] == "DP"

    def test_dp_sama_dengan_nilai_langsung_lunas(self):
        repo = InMemoryRepository()
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        req = ProjectCreateRequest(
            id_proyek="INV-2610-002", tanggal=date(2026, 10, 3), nama_klien="BPK",
            alamat="A", pekerjaan="P", subtotal=5_000_000, diskon=0, dp=5_000_000,
        )
        result = self._run(service.create_project(req, "admin1"))
        assert result["pembayaran"]["tipe"] == "PELUNASAN"

    def test_invoice_duplikat_ditolak(self):
        repo = InMemoryRepository(projects=[make_project("INV-2610-001")])
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        req = ProjectCreateRequest(
            id_proyek="INV-2610-001", tanggal=date(2026, 10, 3), nama_klien="X",
            alamat="A", pekerjaan="P", subtotal=100, diskon=0, dp=0,
        )
        with pytest.raises(AppError) as exc:
            self._run(service.create_project(req, "admin1"))
        assert exc.value.code == "INVOICE_DUPLICATE"
        assert exc.value.status_code == 409

    def test_dp_melebihi_nilai_ditolak(self):
        repo = InMemoryRepository()
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        req = ProjectCreateRequest(
            id_proyek="INV-2610-003", tanggal=date(2026, 10, 3), nama_klien="X",
            alamat="A", pekerjaan="P", subtotal=1_000_000, diskon=0, dp=2_000_000,
        )
        with pytest.raises(AppError) as exc:
            self._run(service.create_project(req, "admin1"))
        assert exc.value.code == "DP_EXCEEDS_VALUE"

    def test_dp_nol_tidak_menulis_pembayaran(self):
        repo = InMemoryRepository()
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        req = ProjectCreateRequest(
            id_proyek="INV-2610-004", tanggal=date(2026, 10, 3), nama_klien="X",
            alamat="A", pekerjaan="P", subtotal=1_000_000, diskon=0, dp=0,
        )
        result = self._run(service.create_project(req, "admin1"))
        assert result["pembayaran"] is None
        assert repo.payments == []


class TestAddPayment:
    def test_pelunasan_penuh(self):
        proj = make_project("INV-2610-001", nilai=10_000_000)
        repo = InMemoryRepository(projects=[proj])
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        result = asyncio.run(service.add_payment("INV-2610-001", PaymentCreateRequest(nominal=10_000_000), "admin1"))
        assert result["pembayaran"]["tipe"] == "PELUNASAN"

    def test_cicilan_kurang_dari_sisa(self):
        proj = make_project("INV-2610-001", nilai=10_000_000)
        repo = InMemoryRepository(projects=[proj])
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        result = asyncio.run(service.add_payment("INV-2610-001", PaymentCreateRequest(nominal=4_000_000), "admin1"))
        assert result["pembayaran"]["tipe"] == "CICILAN"

    def test_overpay_ditolak(self):
        proj = make_project("INV-2610-001", nilai=10_000_000)
        repo = InMemoryRepository(projects=[proj])
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        with pytest.raises(AppError) as exc:
            asyncio.run(service.add_payment("INV-2610-001", PaymentCreateRequest(nominal=11_000_000), "admin1"))
        assert exc.value.code == "PAYMENT_EXCEEDS_BALANCE"
        assert exc.value.details == {"sisa": 10_000_000}

    def test_proyek_tidak_ada_404(self):
        repo = InMemoryRepository()
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        with pytest.raises(AppError) as exc:
            asyncio.run(service.add_payment("TIDAK-ADA", PaymentCreateRequest(nominal=1000), "admin1"))
        assert exc.value.status_code == 404
        assert exc.value.code == "PROJECT_NOT_FOUND"

    def test_proyek_lunas_tidak_bisa_bayar_lagi(self):
        proj = make_project("INV-2610-001", nilai=10_000_000)
        pay = Payment(id_bayar="PAY-2610-001", id_proyek="INV-2610-001", tanggal=date(2026, 10, 5),
                      nominal=10_000_000, tipe="PELUNASAN", bulan_filter="2026-10", dicatat_oleh="admin1")
        repo = InMemoryRepository(projects=[proj], payments=[pay])
        service = ProjectService(make_cache(repo), repo, asyncio.Lock())
        with pytest.raises(AppError) as exc:
            asyncio.run(service.add_payment("INV-2610-001", PaymentCreateRequest(nominal=1000), "admin1"))
        assert exc.value.code == "PAYMENT_EXCEEDS_BALANCE"


class TestCreateExpense:
    def test_nominal_nol_ditolak(self):
        repo = InMemoryRepository()
        service = ExpenseService(make_cache(repo), repo, asyncio.Lock())
        req = ExpenseCreateRequest(tanggal=date(2026, 10, 3), kategori="UPAH", keterangan="x", nominal=0)
        with pytest.raises(AppError) as exc:
            asyncio.run(service.create_expense(req, "admin1"))
        assert exc.value.code == "VALIDATION_ERROR"

    def test_id_dan_tersimpan(self):
        repo = InMemoryRepository(expenses=[
            Expense(id_pengeluaran="OUT-2610-001", tanggal=date(2026, 10, 1), kategori="UPAH",
                    keterangan="x", nominal=100, bulan_filter="2026-10", dibuat_oleh="admin1"),
        ])
        service = ExpenseService(make_cache(repo), repo, asyncio.Lock())
        req = ExpenseCreateRequest(tanggal=date(2026, 10, 3), kategori="UPAH", keterangan="y", nominal=500)
        result = asyncio.run(service.create_expense(req, "admin1"))
        assert result["pengeluaran"]["id_pengeluaran"] == "OUT-2610-002"


class TestSnapshotIncremental:
    def test_append_tidak_membaca_ulang(self):
        proj = make_project("INV-2610-001")
        repo = InMemoryRepository(projects=[proj])
        cache = make_cache(repo)
        # repo berubah di belakang, tapi append tetap benar
        repo.projects.append(make_project("INV-EXTERNAL"))
        asyncio.run(cache.append_project(make_project("INV-2610-002")))
        projects, payments, expenses = asyncio.run(cache.get_data())
        assert [p.id_proyek for p in projects] == ["INV-2610-001", "INV-2610-002"]

    def test_append_payment_dan_expense(self):
        repo = InMemoryRepository()
        cache = make_cache(repo)
        pay = Payment(id_bayar="PAY-2610-001", id_proyek="INV-1", tanggal=date(2026, 10, 3),
                      nominal=100, tipe="DP", bulan_filter="2026-10", dicatat_oleh="admin1")
        asyncio.run(cache.append_payment(pay))
        _, payments, _ = asyncio.run(cache.get_data())
        assert payments[0].id_bayar == "PAY-2610-001"
