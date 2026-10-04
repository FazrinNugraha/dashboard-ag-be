"""Tes tidak bergantung pada file PDF: parser diuji dari teks (fungsi murni)."""
import re
from datetime import date
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.parsers.invoice_parser import parse_invoice_text, parse_rupiah

FIXTURE = Path(__file__).parent / "fixtures" / "invoice_yusuf.txt"


@pytest.fixture
def text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _without_line(text: str, pattern: str) -> str:
    return re.sub(pattern, "", text, flags=re.MULTILINE)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6,700,000", 6_700_000),
        ("21.700.000", 21_700_000),
        ("3,000.000", 3_000_000),
        ("Rp 1.500.000", 1_500_000),
        ("0", 0),
    ],
)
def test_parse_rupiah_menangani_format_campuran(raw, expected):
    assert parse_rupiah(raw) == expected


def test_parse_rupiah_tanpa_angka_error():
    with pytest.raises(ValueError):
        parse_rupiah("Rp -")


def test_invoice_yusuf_terbaca_lengkap(text):
    result = parse_invoice_text(text)

    assert result.nomor_invoice == "INV-2610-001"
    assert result.nama_klien == "BPK YUSUF"
    assert result.alamat == "Buaran, Jakarta Timur"
    assert result.tanggal == date(2026, 10, 3)
    assert result.subtotal == 21_700_000
    assert result.diskon == 700_000
    assert result.nilai_proyek == 21_000_000
    assert result.dp == 10_000_000
    assert result.sisa == 11_000_000
    assert [item.harga for item in result.items] == [6_700_000, 5_400_000, 2_400_000, 4_200_000, 3_000_000]
    assert result.items[1].judul == "Jendela Sleding"
    assert "105cm X 250cm ( 2unit)" in result.items[1].deskripsi
    assert result.pekerjaan.startswith("Pintu Slide&swing ( 2Daun Pintu ), Jendela Sleding")
    assert result.warnings == []


def test_teks_dengan_crlf_tetap_terbaca(text):
    result = parse_invoice_text(text.replace("\n", "\r\n"))
    assert result.nomor_invoice == "INV-2610-001"
    assert result.subtotal == 21_700_000


@pytest.mark.parametrize(("bulan", "angka"), [("Januari", 1), ("Agustus", 8), ("Desember", 12)])
def test_tanggal_bulan_indonesia(text, bulan, angka):
    modified = text.replace("Date:3 Oktober 2026", f"Date:17 {bulan} 2026")
    assert parse_invoice_text(modified).tanggal == date(2026, angka, 17)


def test_nomor_invoice_tidak_ada_ditolak(text):
    modified = _without_line(text, r"^No\. Invoice:.*\n")
    with pytest.raises(AppError) as exc:
        parse_invoice_text(modified)
    assert exc.value.code == "INVOICE_NUMBER_MISSING"
    assert exc.value.status_code == 422


def test_subtotal_hilang_gagal_dengan_detail(text):
    modified = _without_line(text, r"^Subtotal.*\n")
    with pytest.raises(AppError) as exc:
        parse_invoice_text(modified)
    assert exc.value.code == "INVOICE_PARSE_FAILED"
    assert "subtotal" in exc.value.details["missing"]


def test_tanpa_diskon_default_nol_dan_beri_warning_saldo(text):
    modified = _without_line(text, r"^Discount.*\n")
    result = parse_invoice_text(modified)
    assert result.diskon == 0
    assert result.nilai_proyek == 21_700_000
    assert "BALANCE_MISMATCH" in {w.code for w in result.warnings}


def test_tanpa_dp_default_nol(text):
    modified = _without_line(text, r"^DP Rp.*\n")
    result = parse_invoice_text(modified)
    assert result.dp == 0
    assert "BALANCE_MISMATCH" in {w.code for w in result.warnings}


def test_jumlah_item_tidak_sama_subtotal_diberi_warning(text):
    modified = text.replace("Rp 6,700,000", "Rp 6,000,000")
    result = parse_invoice_text(modified)
    assert "ITEMS_SUM_MISMATCH" in {w.code for w in result.warnings}


def test_dp_melebihi_nilai_proyek_diberi_warning(text):
    modified = text.replace("DP Rp 10,000,000", "DP Rp 30,000,000")
    result = parse_invoice_text(modified)
    assert "DP_EXCEEDS_VALUE" in {w.code for w in result.warnings}


def test_diskon_lebih_besar_dari_subtotal_ditolak(text):
    modified = text.replace("Discount Rp 700,000", "Discount Rp 99,999,999")
    with pytest.raises(AppError) as exc:
        parse_invoice_text(modified)
    assert exc.value.code == "INVOICE_PARSE_FAILED"


def test_harga_item_hilang_diberi_warning(text):
    modified = text.replace("Rp 5,400,000\n", "")
    result = parse_invoice_text(modified)
    codes = {w.code for w in result.warnings}
    assert "ITEM_PRICE_MISSING" in codes
