from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.security import get_current_admin
from app.parsers.invoice_parser import parse_invoice_pdf, validate_pdf_bytes
from app.schemas.invoice import ExtractedInvoice

router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"],
    dependencies=[Depends(get_current_admin)],
)


@router.post("/extract", response_model=ExtractedInvoice)
async def extract_invoice(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> ExtractedInvoice:
    """Ekstrak data dari PDF invoice. Tidak menulis apa pun ke Sheets.

    Catatan: pengecekan ukuran terjadi setelah body diterima. Batasi juga ukuran body
    di reverse proxy (mis. client_max_body_size) pada produksi.
    """
    data = await file.read(settings.max_upload_bytes + 1)
    validate_pdf_bytes(data, settings.max_upload_bytes)
    # TODO(M2): tolak nomor invoice yang sudah ada di snapshot (INVOICE_DUPLICATE, 409).
    return await run_in_threadpool(parse_invoice_pdf, data)
