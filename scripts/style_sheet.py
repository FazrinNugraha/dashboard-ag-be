"""Mempercantik tampilan spreadsheet DB_Agungjaya (idempotent, hanya tampilan).

Yang dilakukan (tidak pernah mengubah ISI sel / data):
  - Header berwarna (biru tua, teks putih tebal), baris 1 dibekukan
  - Baris belang (zebra) agar mudah dibaca
  - Format angka uang "Rp 1.000.000" + rata kanan
  - Warna otomatis (conditional formatting) untuk status, tipe, kategori, piutang
  - Filter di header, lebar kolom pas, gridline disembunyikan, warna tab

Aman dijalankan berulang: aturan lama (banding & conditional format) dihapus
dulu lalu dipasang ulang, sehingga tidak menumpuk.

Pakai:
    python scripts/style_sheet.py            # DRY-RUN: hanya menampilkan rencana
    python scripts/style_sheet.py --apply    # benar-benar menerapkan ke spreadsheet

SARAN: duplikasi spreadsheet dulu (File > Make a copy) sebagai cadangan.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.service_account import Credentials

from app.core.config import get_settings

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# ---------------------------------------------------------------------------
# Palet warna (biru profesional). Ubah di sini bila ingin ganti gaya.
# ---------------------------------------------------------------------------
def rgb(hex_color: str) -> dict:
    """Ubah '#RRGGBB' menjadi format warna Sheets API (0.0 - 1.0)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return {"red": r, "green": g, "blue": b}


HEADER_BG = rgb("#1E3A8A")   # biru tua
HEADER_FG = rgb("#FFFFFF")   # putih
BAND_1 = rgb("#FFFFFF")      # baris ganjil
BAND_2 = rgb("#EFF6FF")      # baris genap (biru sangat muda)

# Pasangan (warna latar, warna teks) untuk conditional formatting
GREEN = (rgb("#DCFCE7"), rgb("#166534"))
YELLOW = (rgb("#FEF3C7"), rgb("#92400E"))
BLUE = (rgb("#DBEAFE"), rgb("#1E40AF"))
ROSE = (rgb("#FFE4E6"), rgb("#9F1239"))
TEAL = (rgb("#CCFBF1"), rgb("#115E59"))
SLATE = (rgb("#E2E8F0"), rgb("#334155"))
ORANGE_TEXT = rgb("#C2410C")

MONEY_PATTERN = '"Rp "#,##0'

# ---------------------------------------------------------------------------
# Konfigurasi per tab (indeks kolom 0-based: A=0, B=1, ...)
# ---------------------------------------------------------------------------
TABS = {
    "PEMASUKAN_PROYEK": {
        "tab_color": "#1E3A8A",
        "widths": [130, 100, 170, 200, 260, 120, 110, 130, 90, 100, 130, 130, 110],
        "money": [5, 6, 7, 10, 11],  # subtotal, diskon, nilai, dibayar, sisa
        # (kolom, nilai teks, warna)
        "text_rules": [(12, "LUNAS", GREEN), (12, "DP", YELLOW)],
        # sisa_piutang > 0 -> teks oranye tebal (masih ada tagihan)
        "positive_alert": [11],
    },
    "PEMBAYARAN": {
        "tab_color": "#16A34A",
        "widths": [130, 130, 100, 130, 120, 90, 110],
        "money": [3],
        "text_rules": [(4, "DP", YELLOW), (4, "CICILAN", BLUE), (4, "PELUNASAN", GREEN)],
        "positive_alert": [],
    },
    "PENGELUARAN": {
        "tab_color": "#E11D48",
        "widths": [130, 100, 130, 280, 130, 90, 110, 140],
        "money": [4],
        "text_rules": [
            (2, "BAHAN_BAKU", BLUE),
            (2, "AKSESORIS", TEAL),
            (2, "UPAH", ROSE),
            (2, "OPERASIONAL", YELLOW),
            (2, "LAINNYA", SLATE),
        ],
        "positive_alert": [],
    },
    "REKAP_DASHBOARD": {
        "tab_color": "#64748B",
        "widths": [140, 140, 140, 140, 140, 140],
        "money": [1, 2, 3, 4, 5],
        "text_rules": [],
        "positive_alert": [],
    },
}


def grid(sheet_id: int, rows: int, col_start: int, col_end: int, row_start: int = 0) -> dict:
    """Bentuk GridRange. row_start=1 untuk melewati header."""
    return {
        "sheetId": sheet_id,
        "startRowIndex": row_start,
        "endRowIndex": rows,
        "startColumnIndex": col_start,
        "endColumnIndex": col_end,
    }


def cleanup_requests(sheet_meta: dict) -> list:
    """Hapus banding & conditional format lama agar skrip aman diulang."""
    sheet_id = sheet_meta["properties"]["sheetId"]
    requests = [
        {"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}}
        for b in sheet_meta.get("bandedRanges", [])
    ]
    # Setiap penghapusan menggeser indeks, jadi selalu hapus indeks 0.
    requests += [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
        for _ in sheet_meta.get("conditionalFormats", [])
    ]
    return requests


def style_requests(sheet_id: int, rows: int, cfg: dict) -> list:
    """Semua permintaan tampilan untuk satu tab."""
    ncols = len(cfg["widths"])
    requests = []

    # 1. Warna tab + bekukan baris 1 + sembunyikan gridline
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "tabColorStyle": {"rgbColor": rgb(cfg["tab_color"])},
                "gridProperties": {"frozenRowCount": 1, "hideGridlines": True},
            },
            "fields": "tabColorStyle,gridProperties.frozenRowCount,gridProperties.hideGridlines",
        }
    })

    # 2. Header: latar biru tua, teks putih tebal, rata tengah
    requests.append({
        "repeatCell": {
            "range": grid(sheet_id, 1, 0, ncols),
            "cell": {"userEnteredFormat": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 10},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }
    })
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 34},
            "fields": "pixelSize",
        }
    })

    # 3. Isi tabel: rata tengah vertikal
    requests.append({
        "repeatCell": {
            "range": grid(sheet_id, rows, 0, ncols, row_start=1),
            "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE"}},
            "fields": "userEnteredFormat.verticalAlignment",
        }
    })

    # 4. Baris belang. Memakai bandedRange (sheet-level) sehingga baris baru
    #    yang ditambahkan aplikasi otomatis ikut berwarna.
    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": grid(sheet_id, rows, 0, ncols),
                "rowProperties": {
                    "headerColor": HEADER_BG,
                    "firstBandColor": BAND_1,
                    "secondBandColor": BAND_2,
                },
            }
        }
    })

    # 5. Kolom uang: format Rupiah + rata kanan
    for col in cfg["money"]:
        requests.append({
            "repeatCell": {
                "range": grid(sheet_id, rows, col, col + 1, row_start=1),
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "NUMBER", "pattern": MONEY_PATTERN},
                    "horizontalAlignment": "RIGHT",
                }},
                "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
            }
        })

    # 6. Lebar kolom
    for col, width in enumerate(cfg["widths"]):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        })

    # 7. Filter di baris header
    requests.append({"setBasicFilter": {"filter": {"range": grid(sheet_id, rows, 0, ncols)}}})

    # 8. Warna otomatis berdasarkan teks (status / tipe / kategori)
    for col, text, (bg, fg) in cfg["text_rules"]:
        requests.append({
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [grid(sheet_id, rows, col, col + 1, row_start=1)],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": text}]},
                        "format": {"backgroundColor": bg,
                                   "textFormat": {"foregroundColor": fg, "bold": True}},
                    },
                },
            }
        })

    # 9. Angka > 0 (mis. sisa piutang) -> teks oranye tebal sebagai pengingat
    for col in cfg["positive_alert"]:
        requests.append({
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": [grid(sheet_id, rows, col, col + 1, row_start=1)],
                    "booleanRule": {
                        "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0"}]},
                        "format": {"textFormat": {"foregroundColor": ORANGE_TEXT, "bold": True}},
                    },
                },
            }
        })

    return requests


def main() -> None:
    apply = "--apply" in sys.argv

    settings = get_settings()
    if not settings.SPREADSHEET_ID:
        print("ERROR: SPREADSHEET_ID belum diatur di .env")
        sys.exit(1)
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE or not os.path.exists(settings.GOOGLE_SERVICE_ACCOUNT_FILE):
        print(f"ERROR: file kredensial tidak ditemukan: {settings.GOOGLE_SERVICE_ACCOUNT_FILE!r}")
        sys.exit(1)

    creds = Credentials.from_service_account_file(settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    sh = gspread.authorize(creds).open_by_key(settings.SPREADSHEET_ID)
    print(f"Spreadsheet: {sh.title}")

    metadata = sh.fetch_sheet_metadata()
    meta_by_title = {s["properties"]["title"]: s for s in metadata["sheets"]}

    requests = []
    for tab_name, cfg in TABS.items():
        meta = meta_by_title.get(tab_name)
        if meta is None:
            print(f"- Tab '{tab_name}' tidak ada, dilewati.")
            continue
        props = meta["properties"]
        rows = props["gridProperties"]["rowCount"]
        ncols = len(cfg["widths"])
        # Pastikan grid cukup lebar (mis. kolom H id_proyek di PENGELUARAN).
        if props["gridProperties"]["columnCount"] < ncols:
            requests.append({"appendDimension": {
                "sheetId": props["sheetId"], "dimension": "COLUMNS",
                "length": ncols - props["gridProperties"]["columnCount"],
            }})
        requests += cleanup_requests(meta)
        requests += style_requests(props["sheetId"], rows, cfg)
        print(f"- Tab '{tab_name}': {rows} baris, {ncols} kolom akan dirapikan.")

    print(f"Total {len(requests)} perubahan tampilan.")
    if not apply:
        print("DRY-RUN: belum ada yang diubah. Jalankan dengan --apply untuk menerapkan.")
        return

    sh.batch_update({"requests": requests})
    print("Selesai. Tampilan spreadsheet sudah dirapikan.")


if __name__ == "__main__":
    main()
