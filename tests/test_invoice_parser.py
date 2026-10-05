"""Unit test parser invoice (fungsi murni, tidak memanggil Gemini).

Validasi PDF diuji dengan file yang dibuat saat runtime memakai reportlab
sehingga tidak bergantung pada fixture dan tidak menyentuh jaringan.
"""
import io

import pytest
from reportlab.pdfgen import canvas

from app.core.errors import AppError
from app.parsers.invoice_parser import (
    build_extraction_prompt,
    extract_pdf_text,
    parse_invoice_pdf,
    validate_pdf_bytes,
    validate_pdf_text,
)


def _make_pdf(text: str = "") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if text:
        c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


class TestValidatePdfBytes:
    def test_bukan_pdf_ditolak_415(self):
        with pytest.raises(AppError) as exc:
            validate_pdf_bytes(b"ini bukan pdf", 1024)
        assert exc.value.code == "PDF_INVALID"
        assert exc.value.status_code == 415

    def test_terlalu_besar_ditolak_413(self):
        with pytest.raises(AppError) as exc:
            validate_pdf_bytes(b"%PDF" + b"0" * 100, 10)
        assert exc.value.code == "PDF_TOO_LARGE"
        assert exc.value.status_code == 413

    def test_pdf_valid_lolos(self):
        validate_pdf_bytes(_make_pdf("halo"), 10_000_000)


class TestValidatePdfText:
    def test_pdf_rusak_ditolak_415(self):
        with pytest.raises(AppError) as exc:
            validate_pdf_text(b"%PDF-1.4 rusak total")
        assert exc.value.code == "PDF_INVALID"
        assert exc.value.status_code == 415

    def test_pdf_tanpa_teks_ditolak_422(self):
        with pytest.raises(AppError) as exc:
            validate_pdf_text(_make_pdf())
        assert exc.value.code == "PDF_NO_TEXT"
        assert exc.value.status_code == 422

    def test_pdf_berteks_mengembalikan_teks(self):
        text = validate_pdf_text(_make_pdf("INVOICE TO BPK YUSUF"))
        assert "BPK YUSUF" in text

    def test_extract_pdf_text_rusak_ditolak(self):
        with pytest.raises(AppError) as exc:
            extract_pdf_text(b"%PDF-1.4 rusak total")
        assert exc.value.code == "PDF_INVALID"


class TestParseInvoicePdf:
    def test_tolak_pdf_rusak_tanpa_memanggil_ai(self):
        # Validasi lokal harus menolak sebelum Gemini dipanggil (tanpa jaringan).
        with pytest.raises(AppError) as exc:
            parse_invoice_pdf(b"%PDF-1.4 rusak total")
        assert exc.value.code == "PDF_INVALID"

    def test_tolak_pdf_tanpa_teks(self):
        with pytest.raises(AppError) as exc:
            parse_invoice_pdf(_make_pdf())
        assert exc.value.code == "PDF_NO_TEXT"


def test_prompt_memuat_field_wajib():
    prompt = build_extraction_prompt()
    for field in ("nomor_invoice", "nama_klien", "subtotal", "diskon", "dp", "items"):
        assert field in prompt