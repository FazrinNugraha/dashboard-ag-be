"""Test DashboardService: KPI, delta bulan lalu, trend, breakdown (tanpa Sheets)."""
import asyncio
from datetime import date

from app.domain.snapshot import SnapshotCache
from app.schemas.domain import Expense, Payment, Project
from app.services.dashboard_service import DashboardService


class InMemoryRepository:
    def __init__(self, projects, payments, expenses):
        self._data = (list(projects), list(payments), list(expenses))

    async def read_all(self):
        p, pay, e = self._data
        return list(p), list(pay), list(e)


def project(id_proyek, nilai, bulan):
    return Project(
        id_proyek=id_proyek, tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        nama_klien="K", alamat="A", pekerjaan="P", subtotal=nilai, diskon=0,
        nilai_proyek=nilai, bulan_filter=bulan, dibuat_oleh="admin1",
    )


def payment(id_bayar, id_proyek, nominal, bulan):
    return Payment(
        id_bayar=id_bayar, id_proyek=id_proyek, tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        nominal=nominal, tipe="DP", bulan_filter=bulan, dicatat_oleh="admin1",
    )


def expense(nominal, bulan, kategori="UPAH"):
    return Expense(
        id_pengeluaran="OUT-1", tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        kategori=kategori, keterangan="x", nominal=nominal, bulan_filter=bulan,
        dibuat_oleh="admin1",
    )


def build_service():
    projects = [
        project("INV-2609-001", 10_000_000, "2026-09"),
        project("INV-2610-001", 20_000_000, "2026-10"),
    ]
    payments = [
        payment("PAY-1", "INV-2609-001", 5_000_000, "2026-09"),
        payment("PAY-2", "INV-2610-001", 8_000_000, "2026-10"),
    ]
    expenses = [
        expense(2_000_000, "2026-09"),
        expense(3_000_000, "2026-10"),
    ]
    repo = InMemoryRepository(projects, payments, expenses)
    cache = SnapshotCache(repo, ttl_seconds=30)
    asyncio.run(cache.force_refresh())
    return DashboardService(cache)


class TestDashboardSummary:
    def test_struktur_dan_delta(self):
        result = asyncio.run(build_service().get_dashboard_summary("2026-10"))

        assert result["month"] == "2026-10"
        assert result["all_time"]["omzet"] == 30_000_000
        assert result["all_time"]["jumlah_proyek"] == 2
        assert "generated_at" in result

        # omzet Oktober vs September
        assert result["kpi"]["omzet"]["value"] == 20_000_000
        assert result["kpi"]["omzet"]["prev"] == 10_000_000
        assert result["kpi"]["omzet"]["delta"] == 10_000_000
        assert result["kpi"]["omzet"]["delta_pct"] == 100.0

    def test_laba_bersih_punya_delta(self):
        result = asyncio.run(build_service().get_dashboard_summary("2026-10"))
        laba = result["kpi"]["laba_bersih"]
        # Okt: kas 8jt - peng 3jt = 5jt ; Sep: 5jt - 2jt = 3jt
        assert laba["value"] == 5_000_000
        assert laba["prev"] == 3_000_000
        assert laba["delta"] == 2_000_000

    def test_trend_tujuh_titik_atau_enam(self):
        result = asyncio.run(build_service().get_dashboard_summary("2026-10"))
        assert len(result["trend"]) == 6
        assert result["trend"][-1]["month"] == "2026-10"
        assert result["trend"][-1]["laba_bersih"] == 5_000_000

    def test_expense_breakdown(self):
        result = asyncio.run(build_service().get_dashboard_summary("2026-10"))
        assert result["expense_breakdown"] == [{"kategori": "UPAH", "nominal": 3_000_000}]

    def test_bulan_tanpa_data_tidak_error(self):
        # bulan valid tapi kosong -> delta gagal dihitung? tidak, harus aman
        result = asyncio.run(build_service().get_dashboard_summary("2026-07"))
        assert result["kpi"]["omzet"]["value"] == 0