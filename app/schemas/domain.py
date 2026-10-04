from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import date

class Project(BaseModel):
    id_proyek: str
    tanggal: date
    nama_klien: str
    alamat: str
    pekerjaan: str
    subtotal: int
    diskon: int
    nilai_proyek: int
    bulan_filter: str
    dibuat_oleh: str
    # Fields below are calculated, so they might be empty in Sheets if it's new, 
    # but we will calculate them in metrics.py anyway. Let's make them optional 
    # to avoid parse errors when reading raw sheets if they are missing.
    total_dibayar: int = 0
    sisa_piutang: int = 0
    status_bayar: str = "DP"

class Payment(BaseModel):
    id_bayar: str
    id_proyek: str
    tanggal: date
    nominal: int
    tipe: Literal["DP", "CICILAN", "PELUNASAN"]
    bulan_filter: str
    dicatat_oleh: str

class Expense(BaseModel):
    id_pengeluaran: str
    tanggal: date
    kategori: Literal["BAHAN_BAKU", "AKSESORIS", "UPAH", "OPERASIONAL", "LAINNYA"]
    keterangan: str
    nominal: int
    bulan_filter: str
    dibuat_oleh: str
