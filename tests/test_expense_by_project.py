"""Tes fitur pengeluaran per proyek (tanpa Google Sheets).

Mencakup:
- ExpenseService: simpan id_proyek, tolak proyek tak dikenal, umum bila kosong.
- API GET /projects: menyertakan total_pengeluaran, laba_bersih, margin_pct.
- API GET /expenses?id_proyek=: hanya mengembalikan pengeluaran proyek itu.

Memakai InMemoryRepository dari test_services dan dependency_overrides FastAPI,
sehingga data nyata di Sheets tidak tersentuh.
"""
import asyncio
from datetime import date

import pytest

from app.core.dependencies import get_repository, get_snapshot_cache
from app.core.errors import AppError
from app.main import app
from app.schemas.domain import Expense
from app.services.expense_service import ExpenseCreateRequest, ExpenseService
from tests.conftest import API
from tests.test_services import InMemoryRepository, make_cache, make_project


def _request(id_proyek=None, nominal=500_000) -> ExpenseCreateRequest:
    """Helper: request pengeluaran minimal, proyek opsional."""
    return ExpenseCreateRequest(
        tanggal=date(2026, 10, 5),
        kategori="BAHAN_BAKU",
        keterangan="tes",
        nominal=nominal,
        id_proyek=id_proyek,
    )


def _expense(id_pengeluaran, nominal, id_proyek="") -> Expense:
    """Helper: baris pengeluaran yang sudah ada di data."""
    return Expense(
        id_pengeluaran=id_pengeluaran,
        tanggal=date(2026, 10, 5),
        kategori="UPAH",
        keterangan="tes",
        nominal=nominal,
        bulan_filter="2026-10",
        dibuat_oleh="admin1",
        id_proyek=id_proyek,
    )


class TestExpenseService:
    def _service(self, repo):
        return ExpenseService(make_cache(repo), repo, asyncio.Lock())

    def test_simpan_dengan_proyek(self):
        repo = InMemoryRepository(projects=[make_project("INV-2610-001")])
        result = asyncio.run(self._service(repo).create_expense(_request("INV-2610-001"), "admin1"))
        assert result["pengeluaran"]["id_proyek"] == "INV-2610-001"
        assert repo.expenses[0].id_proyek == "INV-2610-001"

    @pytest.mark.parametrize("kosong", [None, "", "   "])
    def test_tanpa_proyek_dianggap_umum(self, kosong):
        repo = InMemoryRepository(projects=[make_project("INV-2610-001")])
        result = asyncio.run(self._service(repo).create_expense(_request(kosong), "admin1"))
        assert result["pengeluaran"]["id_proyek"] == ""

    def test_proyek_tidak_ada_ditolak_dan_tidak_tertulis(self):
        repo = InMemoryRepository(projects=[make_project("INV-2610-001")])
        with pytest.raises(AppError) as exc:
            asyncio.run(self._service(repo).create_expense(_request("INV-9999-999"), "admin1"))
        assert exc.value.status_code == 404
        assert repo.expenses == []  # tidak ada yang tersimpan


@pytest.fixture
def api_with_data(auth_client):
    """auth_client dengan data palsu: 2 proyek, 3 pengeluaran (2 proyek A, 1 umum)."""
    repo = InMemoryRepository(
        projects=[
            make_project("INV-2610-001", nilai=21_000_000),
            make_project("INV-2610-002", nilai=1_000_000),
        ],
        expenses=[
            _expense("OUT-2610-001", 5_000_000, "INV-2610-001"),
            _expense("OUT-2610-002", 3_000_000, "INV-2610-001"),
            _expense("OUT-2610-003", 400_000),  # umum
        ],
    )
    cache = make_cache(repo)
    app.dependency_overrides[get_snapshot_cache] = lambda: cache
    app.dependency_overrides[get_repository] = lambda: repo
    yield auth_client
    app.dependency_overrides.clear()


class TestProjectsEndpoint:
    def test_daftar_proyek_menyertakan_laba(self, api_with_data):
        r = api_with_data.get(f"{API}/projects")
        assert r.status_code == 200
        by_id = {p["id_proyek"]: p for p in r.json()["data"]}

        a = by_id["INV-2610-001"]
        assert a["total_pengeluaran"] == 8_000_000
        assert a["laba_bersih"] == 13_000_000

        # Proyek tanpa pengeluaran: laba = nilai proyek; pengeluaran umum tidak ikut.
        b = by_id["INV-2610-002"]
        assert b["total_pengeluaran"] == 0
        assert b["laba_bersih"] == 1_000_000

    def test_filter_pengeluaran_per_proyek(self, api_with_data):
        r = api_with_data.get(f"{API}/expenses?id_proyek=INV-2610-001")
        assert r.status_code == 200
        data = r.json()["data"]
        assert {e["id_pengeluaran"] for e in data} == {"OUT-2610-001", "OUT-2610-002"}

    def test_filter_proyek_tanpa_pengeluaran_kosong(self, api_with_data):
        r = api_with_data.get(f"{API}/expenses?id_proyek=INV-2610-002")
        assert r.json()["total"] == 0
