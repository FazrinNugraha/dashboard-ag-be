from datetime import date

from app.domain.metrics import project_profit, total_expense_by_project
from app.schemas.domain import Expense


def _expense(id_pengeluaran: str, nominal: int, id_proyek: str = "") -> Expense:
    """Helper: buat Expense minimal untuk tes."""
    return Expense(
        id_pengeluaran=id_pengeluaran,
        tanggal=date(2026, 10, 5),
        kategori="BAHAN_BAKU",
        keterangan="tes",
        nominal=nominal,
        bulan_filter="2026-10",
        dibuat_oleh="admin1",
        id_proyek=id_proyek,
    )


def test_expense_defaults_to_general():
    """Pengeluaran tanpa id_proyek (data lama) dianggap umum."""
    assert _expense("OUT-2610-001", 1000).id_proyek == ""


def test_total_expense_by_project_ignores_general_expenses():
    expenses = [
        _expense("OUT-2610-001", 5_000_000, "INV-2610-001"),
        _expense("OUT-2610-002", 3_000_000, "INV-2610-001"),
        _expense("OUT-2610-003", 700_000, "INV-2610-002"),
        _expense("OUT-2610-004", 400_000),  # umum: listrik/wifi
    ]
    totals = total_expense_by_project(expenses)
    assert totals == {"INV-2610-001": 8_000_000, "INV-2610-002": 700_000}


def test_project_profit_positive():
    result = project_profit(21_000_000, 8_500_000)
    assert result["total_pengeluaran"] == 8_500_000
    assert result["laba_bersih"] == 12_500_000
    assert result["margin_pct"] == 59.5


def test_project_profit_loss_is_negative():
    result = project_profit(1_000_000, 1_500_000)
    assert result["laba_bersih"] == -500_000
    assert result["margin_pct"] == -50.0


def test_project_profit_without_expense_equals_project_value():
    result = project_profit(10_000_000, 0)
    assert result["laba_bersih"] == 10_000_000
    assert result["margin_pct"] == 100.0


def test_project_profit_zero_value_has_no_margin():
    assert project_profit(0, 0)["margin_pct"] is None
