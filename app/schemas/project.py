from pydantic import BaseModel
from datetime import date
from typing import Optional

class ProjectCreateRequest(BaseModel):
    id_proyek: str
    tanggal: date
    nama_klien: str
    alamat: str
    pekerjaan: str
    subtotal: int
    diskon: int
    dp: int

class PaymentCreateRequest(BaseModel):
    nominal: int
