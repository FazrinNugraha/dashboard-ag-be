"""Tes PDF laporan bergaya kop surat (tanpa Google Sheets)."""
import io
from datetime import date

from pypdf import PdfReader
import pytest

from app.schemas.domain import Expense, Project
from app.services.report_pdf import build_report_pdf, format_date, period_label, rupiah


def _project(id_proyek, nilai, klien="BPK YUSUF") -> Project:
    return Project(
        id_proyek=id_proyek, tanggal=date(2026, 10, 3), nama_klien=klien, alamat="A",
        pekerjaan="P", subtotal=nilai, diskon=0, nilai_proyek=nilai,
        bulan_filter="2026-10", dibuat_oleh="admin1",
    )


def _expense(nominal, kategori="BAHAN_BAKU", id_proyek="") -> Expense:
    return Expense(
        id_pengeluaran="OUT-2610-001", tanggal=date(2026, 10, 5), kategori=kategori,
        keterangan="x", nominal=nominal, bulan_filter="2026-10",
        dibuat_oleh="admin1", id_proyek=id_proyek,
    )


KPI = {
    "omzet": {"value": 13_700_000},
    "kas_masuk": {"value": 6_000_000},
    "pengeluaran": {"value": 400_000},
    "laba_bersih": {"value": 5_600_000, "margin_pct": 93.3},
}


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.mark.parametrize("value,expected", [
    (1_750_000, "Rp 1.750.000"), (0, "Rp 0"), (-500_000, "-Rp 500.000"),
])
def test_rupiah(value, expected):
    assert rupiah(value) == expected


def test_period_label_dan_tanggal():
    assert period_label("month", "2026-10") == "Oktober 2026"
    assert period_label("year", "2026") == "Tahun 2026"
    assert format_date(date(2026, 8, 12)) == "12 Agustus 2026"


def test_pdf_memuat_kop_dan_isi_laporan():
    projects = [_project("INV-2610-001", 21_000_000)]
    expenses = [_expense(8_000_000, id_proyek="INV-2610-001"), _expense(400_000)]
    receivables = [{"id": "INV-2610-001", "klien": "BPK YUSUF", "tanggal": date(2026, 10, 3),
                    "nilai": 21_000_000, "sisa": 11_000_000}]
    content = build_report_pdf(KPI, projects, expenses, receivables,
                               label="Oktober 2026", printed_on=date(2026, 10, 14))
    assert content.startswith(b"%PDF")

    text = _pdf_text(content)
    assert "AGUNG JAYA ALUMINIUM" in text           # kop surat
    assert "LAPORAN KEUANGAN" in text
    assert "Oktober 2026" in text                    # periode terbaca manusia
    assert "Rp 13.700.000" in text                   # format Rupiah
    assert "Rp 13.000.000" in text                   # laba proyek 21jt - 8jt
    assert "Halaman 1 dari" in text                  # footer


def test_pdf_laba_proyek_pakai_total_semua_waktu():
    """project_expenses (semua waktu) menggantikan hitungan dari pengeluaran periode."""
    content = build_report_pdf(
        KPI, [_project("INV-2610-001", 10_000_000)], [], [],
        label="Oktober 2026", printed_on=date(2026, 10, 14),
        project_expenses={"INV-2610-001": 4_000_000},
    )
    assert "Rp 6.000.000" in _pdf_text(content)  # 10jt - 4jt


def test_pdf_data_kosong_tetap_valid():
    content = build_report_pdf(KPI, [], [], [], label="Tahun 2030", printed_on=date(2026, 10, 14))
    text = _pdf_text(content)
    assert "Tidak ada proyek pada periode ini." in text
    assert "Tidak ada piutang saat ini." in text
