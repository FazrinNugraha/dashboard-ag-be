"""Menyiapkan struktur spreadsheet DB_Agungjaya (idempotent).

Dijalankan sekali. Membuat tab, header, freeze baris 1, format angka, validasi
dropdown untuk `tipe`/`kategori`, dan header tebal. Tidak menulis data.

Pakai:
    python scripts/setup_sheet.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValidationConditionType

from app.core.config import get_settings

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

TABS = {
    "PEMASUKAN_PROYEK": [
        "id_proyek", "tanggal", "nama_klien", "alamat", "pekerjaan",
        "subtotal", "diskon", "nilai_proyek", "bulan_filter", "dibuat_oleh",
        "total_dibayar", "sisa_piutang", "status_bayar",
    ],
    "PEMBAYARAN": [
        "id_bayar", "id_proyek", "tanggal", "nominal", "tipe",
        "bulan_filter", "dicatat_oleh",
    ],
    "PENGELUARAN": [
        "id_pengeluaran", "tanggal", "kategori", "keterangan", "nominal",
        "bulan_filter", "dibuat_oleh",
    ],
    "REKAP_DASHBOARD": [
        "Bulan", "Omzet", "Kas Masuk", "Piutang", "Pengeluaran", "Laba Bersih",
    ],
}

# kolom uang (1-based) per tab untuk format angka ribuan.
MONEY_COLUMNS = {
    "PEMASUKAN_PROYEK": [6, 7, 8, 11, 12],  # subtotal, diskon, nilai, dibayar, sisa
    "PEMBAYARAN": [4],
    "PENGELUARAN": [5],
}

# validasi dropdown: tab -> (kolom_1based, nilai)
DROPDOWNS = {
    "PEMBAYARAN": (5, ["DP", "CICILAN", "PELUNASAN"]),
    "PENGELUARAN": (3, ["BAHAN_BAKU", "AKSESORIS", "UPAH", "OPERASIONAL", "LAINNYA"]),
}


def _col_letter(index_1based: int) -> str:
    letters = ""
    while index_1based > 0:
        index_1based, rem = divmod(index_1based - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def main() -> None:
    settings = get_settings()
    if not settings.SPREADSHEET_ID:
        print("ERROR: SPREADSHEET_ID belum diatur di .env")
        sys.exit(1)
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE or not os.path.exists(settings.GOOGLE_SERVICE_ACCOUNT_FILE):
        print(f"ERROR: file kredensial tidak ditemukan: {settings.GOOGLE_SERVICE_ACCOUNT_FILE!r}")
        sys.exit(1)

    print("Autentikasi ke Google Sheets...")
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    client = gspread.authorize(creds)

    print(f"Membuka spreadsheet: {settings.SPREADSHEET_ID}")
    try:
        sh = client.open_by_key(settings.SPREADSHEET_ID)
    except Exception as e:  # noqa: BLE001
        print(f"Gagal membuka spreadsheet: {e}")
        print("Pastikan e-mail Service Account sudah ditambahkan sebagai Editor.")
        sys.exit(1)

    existing = {ws.title: ws for ws in sh.worksheets()}

    for tab_name, headers in TABS.items():
        if tab_name in existing:
            ws = existing[tab_name]
            print(f"Tab '{tab_name}' sudah ada.")
        else:
            print(f"Membuat tab '{tab_name}'...")
            ws = sh.add_worksheet(title=tab_name, rows=1000, cols=max(len(headers), 13))

        # Header + tebal + freeze baris 1
        ws.update(values=[headers], range_name=f"A1:{_col_letter(len(headers))}1",
                  value_input_option="RAW")
        ws.format("1:1", {"textFormat": {"bold": True}})
        ws.freeze(rows=1)

        # Format angka kolom uang
        for col in MONEY_COLUMNS.get(tab_name, []):
            letter = _col_letter(col)
            ws.format(f"{letter}2:{letter}", {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}})

        # Validasi dropdown
        if tab_name in DROPDOWNS:
            col, options = DROPDOWNS[tab_name]
            letter = _col_letter(col)
            ws.add_validation(
                f"{letter}2:{letter}1000",
                ValidationConditionType.one_of_list,
                options,
                strict=False,
                showCustomUi=True,
            )

    print("Selesai. Struktur spreadsheet siap.")


if __name__ == "__main__":
    main()