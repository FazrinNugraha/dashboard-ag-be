from typing import List, Dict, Any, Optional, Callable, Tuple
from datetime import datetime, date
from collections import defaultdict
from app.schemas.domain import Project, Payment, Expense


def total_paid_by_project(payments: List[Payment]) -> Dict[str, int]:
    """Jumlah nominal pembayaran per id_proyek."""
    totals: Dict[str, int] = defaultdict(int)
    for p in payments:
        totals[p.id_proyek] += p.nominal
    return totals


def compute_receivables(
    projects: List[Project],
    payments: List[Payment],
) -> List[Tuple[Project, int, int]]:
    """Daftar piutang berjalan: (proyek, total_dibayar, sisa) untuk sisa > 0.

    Satu-satunya sumber perhitungan piutang di seluruh aplikasi. Dipakai oleh
    KPI, endpoint /receivables, dan laporan agar angkanya konsisten.
    """
    paid = total_paid_by_project(payments)
    result: List[Tuple[Project, int, int]] = []
    for proj in projects:
        total_dibayar = paid.get(proj.id_proyek, 0)
        sisa = max(proj.nilai_proyek - total_dibayar, 0)
        if sisa > 0:
            result.append((proj, total_dibayar, sisa))
    return result


def _summarize_kpi(
    projects: List[Project],
    payments: List[Payment],
    expenses: List[Expense],
    matches: Callable[[str], bool],
) -> Dict[str, Any]:
    omzet = sum(p.nilai_proyek for p in projects if matches(p.bulan_filter))
    kas_masuk = sum(p.nominal for p in payments if matches(p.bulan_filter))
    pengeluaran = sum(e.nominal for e in expenses if matches(e.bulan_filter))

    laba_bersih = kas_masuk - pengeluaran
    margin_pct = round((laba_bersih / kas_masuk * 100), 1) if kas_masuk > 0 else None

    receivables = compute_receivables(projects, payments)
    sisa_piutang_global = sum(sisa for _, _, sisa in receivables)

    return {
        "omzet": {"value": omzet},
        "kas_masuk": {"value": kas_masuk},
        "pengeluaran": {"value": pengeluaran},
        "laba_bersih": {"value": laba_bersih, "margin_pct": margin_pct},
        "sisa_piutang": {"value": sisa_piutang_global, "jumlah_proyek": len(receivables)},
    }


def calculate_kpi(
    projects: List[Project],
    payments: List[Payment],
    expenses: List[Expense],
    month: str,  # Format: YYYY-MM
) -> Dict[str, Any]:
    """KPI untuk satu bulan. Omzet dari tanggal invoice, kas dari tanggal bayar."""
    return _summarize_kpi(projects, payments, expenses, lambda b: b == month)


def calculate_period_kpi(
    projects: List[Project],
    payments: List[Payment],
    expenses: List[Expense],
    period_type: str,  # "month" atau "year"
    period_value: str,  # "YYYY-MM" atau "YYYY"
) -> Dict[str, Any]:
    """KPI untuk satu bulan atau satu tahun (agregat prefix YYYY)."""
    if period_type == "year":
        matches = lambda b: b.startswith(period_value)  # noqa: E731
    else:
        matches = lambda b: b == period_value  # noqa: E731
    return _summarize_kpi(projects, payments, expenses, matches)


def _month_range(end_month: str, count: int) -> List[str]:
    """Daftar `count` bulan kalender berurutan yang berakhir di end_month."""
    try:
        year, month = map(int, end_month.split("-"))
        if not 1 <= month <= 12:
            return []
    except (ValueError, AttributeError):
        return []

    months: List[str] = []
    for offset in range(count - 1, -1, -1):
        total = year * 12 + (month - 1) - offset
        y, m = divmod(total, 12)
        months.append(f"{y}-{m + 1:02d}")
    return months


def get_trend(
    projects: List[Project],
    payments: List[Payment],
    expenses: List[Expense],
    current_month: str,
    months_count: int = 6,
) -> List[Dict[str, Any]]:
    """Tren `months_count` bulan kalender terakhir (termasuk bulan berjalan).

    Setiap titik berisi omzet, kas_masuk, pengeluaran, dan laba_bersih
    (kas_masuk - pengeluaran, basis kas). Bulan tanpa data diisi 0 agar jumlah
    titik grafik konsisten. Semua dihitung dari data yang sudah dimuat sehingga
    pemanggil tidak perlu request per bulan.
    """
    months = _month_range(current_month, months_count)
    if not months:
        return []

    omzet_by_month: Dict[str, int] = defaultdict(int)
    for p in projects:
        omzet_by_month[p.bulan_filter] += p.nilai_proyek

    kas_by_month: Dict[str, int] = defaultdict(int)
    for p in payments:
        kas_by_month[p.bulan_filter] += p.nominal

    pengeluaran_by_month: Dict[str, int] = defaultdict(int)
    for e in expenses:
        pengeluaran_by_month[e.bulan_filter] += e.nominal

    trend: List[Dict[str, Any]] = []
    for m in months:
        kas_masuk = kas_by_month.get(m, 0)
        pengeluaran = pengeluaran_by_month.get(m, 0)
        trend.append(
            {
                "month": m,
                "omzet": omzet_by_month.get(m, 0),
                "kas_masuk": kas_masuk,
                "pengeluaran": pengeluaran,
                "laba_bersih": kas_masuk - pengeluaran,
            }
        )
    return trend


def get_expense_breakdown(expenses: List[Expense], month: str) -> List[Dict[str, Any]]:
    breakdown: Dict[str, int] = defaultdict(int)
    for e in expenses:
        if e.bulan_filter == month:
            breakdown[e.kategori] += e.nominal

    return [{"kategori": k, "nominal": v} for k, v in breakdown.items() if v > 0]
