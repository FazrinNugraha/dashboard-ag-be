"""Parser invoice PDF AGUNGJAYA ALUMINIUM (PRD 6.6).

Berbasis label + regex (bukan koordinat) karena PDF berasal dari cetak browser
dan tata letaknya dapat bergeser. Semua fungsi parsing murni (input teks, output model)
sehingga mudah diuji tanpa file PDF.
"""
from __future__ import annotations

import io
import re
from datetime import date

from app.core.errors import AppError
from app.schemas.invoice import ExtractedInvoice, InvoiceItem, InvoiceWarning

NOMOR_RE = re.compile(r"\bINV-\d{4}-\d{3,}\b", re.IGNORECASE)

BULAN = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "agu": 8, "agt": 8,
    "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

_TANGGAL_RE = re.compile(r"Date[ \t]*:?[ \t]*(\d{1,2})[ \t]+([A-Za-z]+)[ \t]+(\d{4})", re.IGNORECASE)
_KLIEN_RE = re.compile(r"INVOICE[ \t]*TO[ \t]*\n(.*?)\n[ \t]*FROM\b", re.IGNORECASE | re.DOTALL)
_ITEMS_RE = re.compile(
    r"NO[ \t]+DESKRIPSI[ \t]+PESANAN[ \t]+TOTAL[ \t]*\n(.*?)(?=\n[ \t]*SPESIFIKASI[ \t]+BAHAN|\n[ \t]*Subtotal)",
    re.IGNORECASE | re.DOTALL,
)
_ITEM_START = re.compile(r"^(\d+)\.\s+(.*)$")
_PRICE_LINE = re.compile(r"^Rp[ \t]*([\d.,]+)$", re.IGNORECASE)
PEKERJAAN_MAX = 200


def parse_rupiah(raw: str) -> int:
    """Ambil digit saja. Menangani format campuran: '6,700,000', '21.700.000', '3,000.000'."""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise ValueError(f"Tidak ada angka pada: {raw!r}")
    return int(digits)


def _amount_after(label: str, text: str) -> int | None:
    pattern = rf"^[ \t]*(?:{label})[ \t]*:?[ \t]*Rp[ \t]*([\d.,]+)"
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    try:
        return parse_rupiah(match.group(1))
    except ValueError:
        return None


def _find_tanggal(text: str) -> date | None:
    match = _TANGGAL_RE.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = BULAN.get(month_name.lower())
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def _find_klien(text: str) -> tuple[str, str] | None:
    match = _KLIEN_RE.search(text)
    if not match:
        return None
    lines = [ln.strip() for ln in match.group(1).splitlines() if ln.strip()]
    if not lines:
        return None
    alamat = ", ".join(lines[1:])
    alamat = re.sub(r"\s+,", ",", alamat)
    alamat = re.sub(r"\s{2,}", " ", alamat).strip()
    return lines[0], alamat


def _parse_items(text: str, warnings: list[InvoiceWarning]) -> list[InvoiceItem]:
    match = _ITEMS_RE.search(text)
    if not match:
        return []

    items: list[InvoiceItem] = []
    current: list[str] | None = None

    def flag_missing_price() -> None:
        warnings.append(
            InvoiceWarning(
                code="ITEM_PRICE_MISSING",
                message=f"Harga tidak ditemukan untuk item: {current[0] if current else '?'}",
            )
        )

    for raw in match.group(1).splitlines():
        line = raw.strip()
        if not line:
            continue
        price = _PRICE_LINE.match(line)
        if price:
            if current is not None:
                items.append(
                    InvoiceItem(
                        judul=current[0],
                        deskripsi=", ".join(current),
                        harga=parse_rupiah(price.group(1)),
                    )
                )
                current = None
            continue
        start = _ITEM_START.match(line)
        if start:
            if current is not None:
                flag_missing_price()
            current = [start.group(2).strip()]
        elif current is not None:
            current.append(line)

    if current is not None:
        flag_missing_price()
    return items


def parse_invoice_text(text: str) -> ExtractedInvoice:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    nomor_match = NOMOR_RE.search(text)
    if not nomor_match:
        raise AppError(
            "INVOICE_NUMBER_MISSING",
            "Nomor invoice tidak ditemukan di PDF. Pastikan invoice generator mencetak "
            "nomor dengan format INV-YYMM-NNN.",
            422,
        )
    nomor = nomor_match.group(0).upper()

    tanggal = _find_tanggal(text)
    klien = _find_klien(text)
    subtotal = _amount_after("Subtotal", text)

    missing = [
        name
        for name, value in (("tanggal", tanggal), ("nama_klien", klien), ("subtotal", subtotal))
        if value is None
    ]
    if missing:
        raise AppError(
            "INVOICE_PARSE_FAILED",
            "Sebagian data wajib tidak ditemukan di PDF.",
            422,
            {"missing": missing},
        )
    assert tanggal is not None and klien is not None and subtotal is not None

    diskon = _amount_after("Discount|Diskon", text) or 0
    dp = _amount_after("DP", text) or 0
    nilai_proyek = subtotal - diskon
    if nilai_proyek < 0:
        raise AppError(
            "INVOICE_PARSE_FAILED",
            "Diskon lebih besar dari subtotal.",
            422,
            {"subtotal": subtotal, "diskon": diskon},
        )

    sisa_pdf = _amount_after(r"Sisa[ \t]+Pembayaran", text)
    sisa = sisa_pdf if sisa_pdf is not None else nilai_proyek - dp

    warnings: list[InvoiceWarning] = []
    items = _parse_items(text, warnings)

    if items and sum(item.harga for item in items) != subtotal:
        warnings.append(
            InvoiceWarning(
                code="ITEMS_SUM_MISMATCH",
                message="Jumlah harga item tidak sama dengan subtotal.",
            )
        )
    if sisa_pdf is not None and sisa_pdf != nilai_proyek - dp:
        warnings.append(
            InvoiceWarning(
                code="BALANCE_MISMATCH",
                message="Sisa pembayaran di PDF tidak sama dengan subtotal - diskon - DP.",
            )
        )
    if dp > nilai_proyek:
        warnings.append(
            InvoiceWarning(code="DP_EXCEEDS_VALUE", message="DP melebihi nilai proyek.")
        )

    pekerjaan = ", ".join(item.judul for item in items)[:PEKERJAAN_MAX]

    nama_klien, alamat = klien
    return ExtractedInvoice(
        nomor_invoice=nomor,
        nama_klien=nama_klien,
        alamat=alamat,
        tanggal=tanggal,
        pekerjaan=pekerjaan,
        items=items,
        subtotal=subtotal,
        diskon=diskon,
        nilai_proyek=nilai_proyek,
        dp=dp,
        sisa=sisa,
        warnings=warnings,
    )


def validate_pdf_bytes(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise AppError(
            "PDF_TOO_LARGE",
            f"Ukuran file melebihi batas {max_bytes // (1024 * 1024)} MB.",
            413,
        )
    if not data.startswith(b"%PDF"):
        raise AppError("PDF_INVALID", "File bukan PDF yang valid.", 415)


def extract_text_from_pdf(data: bytes) -> str:
    import pdfplumber  # impor lokal agar tes parser teks tidak butuh pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception as exc:  # pdfplumber/pdfminer melempar beragam tipe untuk PDF rusak
        raise AppError("PDF_INVALID", "File PDF rusak atau tidak dapat dibaca.", 415) from exc

    if not text.strip():
        raise AppError(
            "PDF_NO_TEXT",
            "PDF tidak berisi teks (kemungkinan hasil scan/gambar).",
            422,
        )
    return text


def parse_invoice_pdf(data: bytes) -> ExtractedInvoice:
    return parse_invoice_text(extract_text_from_pdf(data))
