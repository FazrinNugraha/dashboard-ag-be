"""Tes Excel laporan keuangan bergaya kop surat perusahaan (tanpa Google Sheets)."""
import io
from datetime import date
from openpyxl import load_workbook

from app.schemas.domain import Expense, Project
from app.services.report_excel import (
    build_report_excel,
    COMPANY,
    MONEY_FMT,
    PROFIT_FMT,
    PCT_FMT,
    DATE_FMT,
)


def _project(id_proyek, nilai, klien="BPK YUSUF") -> Project:
    return Project(
        id_proyek=id_proyek,
        tanggal=date(2026, 10, 3),
        nama_klien=klien,
        alamat="Jl. Buaran",
        pekerjaan="Kusen Aluminium 4 unit",
        subtotal=nilai,
        diskon=0,
        nilai_proyek=nilai,
        bulan_filter="2026-10",
        dibuat_oleh="admin1",
        status_bayar="DP",
    )


def _expense(nominal, kategori="BAHAN_BAKU", id_proyek="") -> Expense:
    return Expense(
        id_pengeluaran="OUT-2610-001",
        tanggal=date(2026, 10, 5),
        kategori=kategori,
        keterangan="Beli profil aluminium",
        nominal=nominal,
        bulan_filter="2026-10",
        dibuat_oleh="admin1",
        id_proyek=id_proyek,
    )


KPI = {
    "omzet": {"value": 21_000_000},
    "kas_masuk": {"value": 10_000_000},
    "pengeluaran": {"value": 8_000_000},
    "laba_bersih": {"value": 2_000_000, "margin_pct": 20.0},
}


def test_excel_struktur_dan_kop():
    projects = [_project("INV-2610-001", 21_000_000)]
    expenses = [_expense(8_000_000, id_proyek="INV-2610-001")]
    receivables = [
        {
            "id": "INV-2610-001",
            "klien": "BPK YUSUF",
            "tanggal": date(2026, 10, 3),
            "nilai": 21_000_000,
            "sisa": 11_000_000,
        }
    ]

    content = build_report_excel(
        KPI,
        projects,
        expenses,
        receivables,
        label="Oktober 2026",
        printed_on=date(2026, 10, 14),
        project_expenses={"INV-2610-001": 8_000_000},
    )

    assert content[:2] == b"PK"  # File ZIP / XLSX valid
    wb = load_workbook(io.BytesIO(content))

    # Cek 4 sheet ada
    assert wb.sheetnames == ["Ringkasan KPI", "Proyek", "Pengeluaran", "Piutang"]

    # Cek kop surat di sheet Ringkasan KPI
    ws1 = wb["Ringkasan KPI"]
    assert ws1.cell(1, 1).value == COMPANY["name"]
    assert ws1.cell(2, 1).value == COMPANY["tagline"]
    assert ws1.cell(3, 1).value == COMPANY["address"]
    assert "Periode: Oktober 2026" in str(ws1.cell(6, 1).value)

    # Cek nilai laba bersih di sheet Ringkasan KPI
    # Header di baris 8, data 4 baris, total di baris 13
    assert ws1.cell(9, 1).value == "Omzet (nilai invoice terbit)"
    assert ws1.cell(9, 2).value == 21_000_000
    assert ws1.cell(9, 2).number_format == MONEY_FMT


def test_excel_proyek_laba_per_proyek():
    projects = [_project("INV-2610-001", 21_000_000)]
    content = build_report_excel(
        KPI,
        projects,
        [],
        [],
        label="Oktober 2026",
        printed_on=date(2026, 10, 14),
        project_expenses={"INV-2610-001": 8_000_000},
    )

    wb = load_workbook(io.BytesIO(content))
    ws = wb["Proyek"]

    # Baris data proyek pertama di baris 9 (setelah header baris 8)
    row = 9
    assert ws.cell(row, 1).value == "INV-2610-001"
    assert ws.cell(row, 3).value == "BPK YUSUF"
    assert ws.cell(row, 5).value == 21_000_000   # Nilai proyek
    assert ws.cell(row, 6).value == 8_000_000    # Pengeluaran proyek
    assert ws.cell(row, 7).value == 13_000_000   # Laba bersih (21jt - 8jt)
    assert ws.cell(row, 7).number_format == PROFIT_FMT
    assert ws.cell(row, 9).value == "DP"         # Status bayar


def test_excel_data_kosong_tetap_terbuat():
    content = build_report_excel(
        KPI,
        [],
        [],
        [],
        label="Tahun 2030",
        printed_on=date(2026, 10, 14),
    )
    assert content[:2] == b"PK"
    wb = load_workbook(io.BytesIO(content))
    assert len(wb.sheetnames) == 4
