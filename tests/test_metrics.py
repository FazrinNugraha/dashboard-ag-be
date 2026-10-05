"""Unit test domain/metrics.py (fungsi murni, tanpa Sheets)."""
from datetime import date

from app.domain.metrics import (
    calculate_kpi,
    calculate_period_kpi,
    compute_receivables,
    get_expense_breakdown,
    get_trend,
)
from app.schemas.domain import Expense, Payment, Project


def project(id_proyek, nilai=10_000_000, bulan="2026-10"):
    return Project(
        id_proyek=id_proyek,
        tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        nama_klien="K",
        alamat="A",
        pekerjaan="P",
        subtotal=nilai,
        diskon=0,
        nilai_proyek=nilai,
        bulan_filter=bulan,
        dibuat_oleh="admin1",
    )


def payment(id_bayar, id_proyek, nominal, bulan="2026-10", tipe="DP"):
    return Payment(
        id_bayar=id_bayar,
        id_proyek=id_proyek,
        tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        nominal=nominal,
        tipe=tipe,
        bulan_filter=bulan,
        dicatat_oleh="admin1",
    )


def expense(nominal, bulan="2026-10", kategori="UPAH"):
    return Expense(
        id_pengeluaran="OUT-1",
        tanggal=date(int(bulan[:4]), int(bulan[5:7]), 1),
        kategori=kategori,
        keterangan="x",
        nominal=nominal,
        bulan_filter=bulan,
        dibuat_oleh="admin1",
    )


class TestCalculateKpi:
    def test_omzet_vs_kas_bulan_berbeda(self):
        # Omzet di Okt (invoice), DP dibayar Okt, pelunasan dibayar Nov.
        projects = [project("INV-1", nilai=21_000_000, bulan="2026-10")]
        payments = [
            payment("PAY-1", "INV-1", 10_000_000, bulan="2026-10"),
            payment("PAY-2", "INV-1", 11_000_000, bulan="2026-11"),
        ]

        okt = calculate_kpi(projects, payments, [], "2026-10")
        nov = calculate_kpi(projects, payments, [], "2026-11")

        assert okt["omzet"]["value"] == 21_000_000
        assert okt["kas_masuk"]["value"] == 10_000_000
        # Nov tidak menambah omzet, hanya kas
        assert nov["omzet"]["value"] == 0
        assert nov["kas_masuk"]["value"] == 11_000_000

    def test_laba_dan_margin(self):
        payments = [payment("PAY-1", "INV-1", 10_000_000)]
        expenses = [expense(4_000_000)]
        kpi = calculate_kpi([], payments, expenses, "2026-10")
        assert kpi["laba_bersih"]["value"] == 6_000_000
        assert kpi["laba_bersih"]["margin_pct"] == 60.0

    def test_margin_none_saat_kas_nol(self):
        kpi = calculate_kpi([], [], [expense(1_000_000)], "2026-10")
        assert kpi["laba_bersih"]["value"] == -1_000_000
        assert kpi["laba_bersih"]["margin_pct"] is None

    def test_sisa_piutang_global(self):
        projects = [project("INV-1", 10_000_000), project("INV-2", 5_000_000)]
        payments = [payment("PAY-1", "INV-1", 10_000_000)]  # INV-1 lunas
        kpi = calculate_kpi(projects, payments, [], "2026-10")
        assert kpi["sisa_piutang"]["value"] == 5_000_000
        assert kpi["sisa_piutang"]["jumlah_proyek"] == 1

    def test_bulan_tanpa_data_semua_nol(self):
        kpi = calculate_kpi([project("INV-1")], [], [], "2030-01")
        assert kpi["omzet"]["value"] == 0
        assert kpi["kas_masuk"]["value"] == 0
        assert kpi["pengeluaran"]["value"] == 0


class TestPeriodKpi:
    def test_agregat_tahun(self):
        projects = [
            project("INV-1", 10_000_000, "2026-01"),
            project("INV-2", 5_000_000, "2026-12"),
            project("INV-3", 99_000_000, "2025-12"),
        ]
        payments = [
            payment("PAY-1", "INV-1", 3_000_000, "2026-02"),
            payment("PAY-2", "INV-2", 2_000_000, "2026-12"),
            payment("PAY-3", "INV-3", 1_000_000, "2025-12"),
        ]
        kpi = calculate_period_kpi(projects, payments, [], "year", "2026")
        assert kpi["omzet"]["value"] == 15_000_000
        assert kpi["kas_masuk"]["value"] == 5_000_000

    def test_bulan_sama_dengan_calculate_kpi(self):
        projects = [project("INV-1", 7_000_000, "2026-05")]
        payments = [payment("PAY-1", "INV-1", 1_000_000, "2026-05")]
        a = calculate_period_kpi(projects, payments, [], "month", "2026-05")
        b = calculate_kpi(projects, payments, [], "2026-05")
        assert a == b


class TestComputeReceivables:
    def test_hanya_sisa_positif(self):
        projects = [project("INV-1", 10_000_000), project("INV-2", 5_000_000)]
        payments = [payment("PAY-1", "INV-1", 10_000_000)]
        result = compute_receivables(projects, payments)
        assert [p.id_proyek for p, _, _ in result] == ["INV-2"]
        assert result[0][1] == 0
        assert result[0][2] == 5_000_000

    def test_overpay_tidak_bikin_sisa_negatif(self):
        projects = [project("INV-1", 5_000_000)]
        payments = [payment("PAY-1", "INV-1", 6_000_000)]
        assert compute_receivables(projects, payments) == []


class TestTrend:
    def test_enam_bulan_kalender_berurutan(self):
        projects = [project("INV-1", 3_000_000, "2026-10")]
        trend = get_trend(projects, [], [], "2026-10", 6)
        assert [t["month"] for t in trend] == [
            "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
        ]
        # bulan tanpa data bernilai 0, bulan berjalan berisi omzet
        assert trend[-1]["omzet"] == 3_000_000
        assert trend[0]["omzet"] == 0

    def test_laba_bersih_per_bulan(self):
        projects = [project("INV-1", 5_000_000, "2026-10")]
        payments = [payment("PAY-1", "INV-1", 4_000_000, "2026-10")]
        expenses = [expense(1_500_000, "2026-10")]
        trend = get_trend(projects, payments, expenses, "2026-10", 6)
        titik = trend[-1]
        assert titik["omzet"] == 5_000_000
        assert titik["kas_masuk"] == 4_000_000
        assert titik["pengeluaran"] == 1_500_000
        assert titik["laba_bersih"] == 2_500_000
        # bulan tanpa data
        assert trend[0]["laba_bersih"] == 0

    def test_lintas_tahun(self):
        trend = get_trend([], [], [], "2026-02", 6)
        assert [t["month"] for t in trend] == [
            "2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
        ]

    def test_bulan_malformed_mengembalikan_kosong(self):
        assert get_trend([], [], [], "tidak-valid", 6) == []
        assert get_trend([], [], [], "2026-13", 6) == []


class TestExpenseBreakdown:
    def test_hanya_bulan_terpilih_dan_positif(self):
        expenses = [
            expense(1_000_000, "2026-10", "UPAH"),
            expense(2_000_000, "2026-10", "BAHAN_BAKU"),
            expense(500_000, "2026-11", "UPAH"),
        ]
        result = get_expense_breakdown(expenses, "2026-10")
        assert {r["kategori"]: r["nominal"] for r in result} == {
            "UPAH": 1_000_000,
            "BAHAN_BAKU": 2_000_000,
        }
