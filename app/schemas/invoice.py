"""Skema Pydantic untuk hasil ekstraksi invoice."""
from datetime import date

from pydantic import BaseModel, Field


class InvoiceItem(BaseModel):
    judul: str
    deskripsi: str
    harga: int = Field(ge=0)


class InvoiceWarning(BaseModel):
    code: str
    message: str


class ExtractedInvoice(BaseModel):
    nomor_invoice: str
    nama_klien: str
    alamat: str
    tanggal: date
    pekerjaan: str
    items: list[InvoiceItem]
    subtotal: int
    diskon: int
    nilai_proyek: int
    dp: int
    sisa: int
    warnings: list[InvoiceWarning]
