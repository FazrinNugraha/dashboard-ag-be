"""Parser invoice PDF AGUNGJAYA ALUMINIUM menggunakan Gemini API."""
from __future__ import annotations

import io
from datetime import date

from app.core.errors import AppError
from app.schemas.invoice import ExtractedInvoice


def validate_pdf_bytes(data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise AppError(
            "PDF_TOO_LARGE",
            f"Ukuran file melebihi batas {max_bytes // (1024 * 1024)} MB.",
            413,
        )
    if not data.startswith(b"%PDF"):
        raise AppError("PDF_INVALID", "File bukan PDF yang valid.", 415)


def validate_pdf_readable(data: bytes) -> None:
    """Pastikan byte PDF dapat dibuka (struktur valid, tidak rusak/terenkripsi).

    Hanya menolak PDF yang benar-benar tidak dapat dibaca. PDF hasil scan atau
    gambar (tanpa lapisan teks) tetap valid di sini karena Gemini dapat membaca
    isinya secara visual.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AppError("PDF_INVALID", "File PDF terenkripsi tidak didukung.", 415)
        if len(reader.pages) == 0:
            raise AppError("PDF_INVALID", "PDF tidak memiliki halaman.", 415)
    except AppError:
        raise
    except Exception:
        raise AppError("PDF_INVALID", "File PDF tidak dapat dibaca.", 415)


def build_extraction_prompt() -> str:
    return """
    Ekstrak data dari dokumen invoice berikut ini dengan cermat. Dokumen dapat
    berupa teks maupun hasil scan/gambar, jadi baca seluruh isi dokumen secara
    visual bila perlu.
    Aturan:
    1. nomor_invoice: Cari pola INV-YYMM-NNN (contoh INV-2610-001). Jika sama sekali tidak ada, buat "INV-AUTO-9999".
    2. nama_klien: Ambil nama orang/perusahaan setelah tulisan INVOICE TO.
    3. alamat: Ambil alamat klien.
    4. tanggal: Ambil tanggal invoice (format YYYY-MM-DD). Jika tidak ada, gunakan tanggal hari ini.
    5. items: Daftar pesanan (tiap pesanan wajib ada judul, deskripsi, harga).
    6. pekerjaan: Gabungkan judul seluruh item menjadi satu string (pisahkan dengan koma).
    7. subtotal: Total sebelum diskon.
    8. diskon: Jika ada potongan. Jika tidak ada = 0.
    9. nilai_proyek: subtotal - diskon.
    10. dp: Uang muka (Down Payment). Jika tidak ada = 0.
    11. sisa: Sisa pembayaran (nilai_proyek - dp).

    Dokumen PDF Invoice dilampirkan.
    """


def parse_invoice_pdf(data: bytes) -> ExtractedInvoice:
    # Tolak hanya PDF yang rusak. PDF hasil scan/gambar tetap diteruskan ke AI
    # karena Gemini membaca dokumen secara visual.
    validate_pdf_readable(data)

    from google import genai
    from google.genai import types
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise AppError("GEMINI_KEY_MISSING", "GEMINI_API_KEY belum dikonfigurasi.", 500)

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    try:
        pdf_part = types.Part.from_bytes(data=data, mime_type="application/pdf")

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[build_extraction_prompt(), pdf_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractedInvoice,
            ),
        )
        return ExtractedInvoice.model_validate_json(response.text)
    except AppError:
        raise
    except Exception as e:
        raise AppError("AI_EXTRACTION_FAILED", f"Gagal mengekstrak invoice dengan AI: {e}", 500)