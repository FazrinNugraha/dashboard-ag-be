"""Pembuat Excel (XLSX) laporan keuangan dengan tampilan profesional.

Gaya mengikuti laporan PDF: kop perusahaan di atas tiap sheet, header navy,
baris belang, format Rupiah, baris total, filter, dan pengaturan cetak.
Identitas perusahaan & palet warna dipakai bersama dari `report_pdf` agar
PDF dan Excel selalu seragam.

Nilai ditulis sebagai angka/tanggal asli (bukan teks) sehingga tetap bisa
dijumlah, difilter, dan diurutkan di Excel.
"""
import io
from datetime import date
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.domain import Expense, Project
from app.services.report_pdf import CATEGORY_LABELS, COMPANY, format_date

# --- Palet (hex tanpa '#', format openpyxl) ---------------------------------
NAVY = "1E3A5F"
BAND = "DCE6F1"
TOTAL_BG = "EEF2F7"
GREEN_BG, GREEN_FG = "DCFCE7", "166534"
YELLOW_BG, YELLOW_FG = "FEF3C7", "92400E"

# Format angka Excel. Laba: hijau bila untung, merah bila rugi.
MONEY_FMT = '"Rp" #,##0'
PROFIT_FMT = '[Color10]"Rp" #,##0;[Red]-"Rp" #,##0'
PCT_FMT = "0.0%"
DATE_FMT = "dd/mm/yyyy"

# Baris tetap di tiap sheet: kop (1-3), judul (5-6), header tabel (8)
TITLE_ROW = 5
PERIOD_ROW = 6
HEADER_ROW = 8

_THIN = Side(style="thin", color="000000")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", start_color=color, end_color=color)


def _letterhead(ws: Worksheet, ncols: int, title: str, label: str) -> None:
    """Kop perusahaan (merge selebar tabel) + garis navy + judul sheet & periode."""
    def merged(row: int, text: str, font: Font, height: float | None = None):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if height:
            ws.row_dimensions[row].height = height

    merged(1, COMPANY["name"], Font(name="Times New Roman", size=18, bold=True, color=NAVY), 28)
    merged(2, COMPANY["tagline"], Font(name="Times New Roman", size=10, italic=True))
    merged(3, COMPANY["address"], Font(name="Times New Roman", size=10))
    # Garis navy tebal di bawah kop
    for col in range(1, ncols + 1):
        ws.cell(row=3, column=col).border = Border(bottom=Side(style="thick", color=NAVY))
    merged(TITLE_ROW, title, Font(name="Times New Roman", size=13, bold=True), 22)
    merged(PERIOD_ROW, f"Periode: {label}" if label else "", Font(name="Times New Roman", size=10))


def _table(
    ws: Worksheet,
    headers: List[str],
    rows: List[list],
    widths: List[float],
    money: tuple = (),
    profit: tuple = (),
    pct: tuple = (),
    dates: tuple = (),
    center: tuple = (),
    total: Optional[list] = None,
) -> int:
    """Tulis tabel mulai HEADER_ROW. Kolom 1-based. Mengembalikan baris terakhir.

    money/profit/pct/dates : kolom yang diberi format angka tertentu.
    center                 : kolom rata tengah (mis. No, Status).
    total                  : baris total (tebal) di akhir tabel.
    """
    ncols = len(headers)

    # Header navy
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=HEADER_ROW, column=c, value=h)
        cell.font = Font(name="Times New Roman", size=10, bold=True, color="FFFFFF")
        cell.fill = _fill(NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[HEADER_ROW].height = 24

    def style_cell(cell, c: int, bold: bool = False):
        cell.font = Font(name="Times New Roman", size=10, bold=bold)
        cell.border = _BORDER
        cell.alignment = Alignment(
            horizontal="center" if c in center else "right" if c in money + profit + pct else "left",
            vertical="center", wrap_text=True,
        )
        if c in money:
            cell.number_format = MONEY_FMT
        elif c in profit:
            cell.number_format = PROFIT_FMT
        elif c in pct:
            cell.number_format = PCT_FMT
        elif c in dates:
            cell.number_format = DATE_FMT

    # Data (baris genap diberi warna belang)
    for r, values in enumerate(rows):
        row_idx = HEADER_ROW + 1 + r
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=c, value=v)
            style_cell(cell, c)
            if r % 2 == 1:
                cell.fill = _fill(BAND)

    last = HEADER_ROW + len(rows)

    # Baris total
    if total:
        last += 1
        for c, v in enumerate(total, 1):
            cell = ws.cell(row=last, column=c, value=v)
            style_cell(cell, c, bold=True)
            cell.fill = _fill(TOTAL_BG)

    # Lebar kolom, bekukan header, filter, dan pengaturan cetak
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=HEADER_ROW + 1, column=1)
    if rows:
        data_end = HEADER_ROW + len(rows)
        ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(ncols)}{data_end}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    return last


def _footer_note(ws: Worksheet, ncols: int, last_row: int, printed_on: date) -> None:
    """Catatan kecil di bawah tabel: tanggal cetak."""
    ws.merge_cells(start_row=last_row + 2, start_column=1, end_row=last_row + 2, end_column=ncols)
    cell = ws.cell(row=last_row + 2, column=1, value=f"Dicetak pada {format_date(printed_on)}")
    cell.font = Font(name="Times New Roman", size=9, italic=True, color="475569")
    cell.alignment = Alignment(horizontal="right")


def _status_fill(ws: Worksheet, col: int, first_row: int, last_row: int) -> None:
    """Warnai sel status: LUNAS hijau, DP kuning."""
    for r in range(first_row, last_row + 1):
        cell = ws.cell(row=r, column=col)
        if cell.value == "LUNAS":
            cell.fill, cell.font = _fill(GREEN_BG), Font(name="Times New Roman", size=10, bold=True, color=GREEN_FG)
        elif cell.value == "DP":
            cell.fill, cell.font = _fill(YELLOW_BG), Font(name="Times New Roman", size=10, bold=True, color=YELLOW_FG)


def build_report_excel(
    kpi: dict,
    projects: List[Project],
    expenses: List[Expense],
    receivables: List[dict],
    label: str,
    printed_on: date,
    project_expenses: Optional[Dict[str, int]] = None,
) -> bytes:
    """Bangun workbook laporan (4 sheet).

    project_expenses : total pengeluaran SEMUA waktu per id_proyek untuk laba
                       per proyek. Bila None dihitung dari `expenses` periode.
    """
    if project_expenses is None:
        project_expenses = {}
        for e in expenses:
            if e.id_proyek:
                project_expenses[e.id_proyek] = project_expenses.get(e.id_proyek, 0) + e.nominal

    wb = Workbook()

    # 1. Ringkasan KPI -------------------------------------------------------
    ws = wb.active
    ws.title = "Ringkasan KPI"
    ws.sheet_properties.tabColor = NAVY
    margin = kpi["laba_bersih"].get("margin_pct")
    _letterhead(ws, 2, "LAPORAN KEUANGAN - RINGKASAN", label)
    last = _table(
        ws, ["Keterangan", "Nilai"],
        [
            ["Omzet (nilai invoice terbit)", kpi["omzet"]["value"]],
            ["Kas Masuk (pembayaran diterima)", kpi["kas_masuk"]["value"]],
            ["Total Pengeluaran", kpi["pengeluaran"]["value"]],
            ["Margin Laba", margin / 100 if margin is not None else "-"],
        ],
        [44, 24], money=(2,),
        total=["Laba Bersih (Kas Masuk - Pengeluaran)", kpi["laba_bersih"]["value"]],
    )
    ws.cell(row=last, column=2).number_format = PROFIT_FMT
    # Baris margin berformat persen (baris data ke-4)
    margin_cell = ws.cell(row=HEADER_ROW + 4, column=2)
    if margin is not None:
        margin_cell.number_format = PCT_FMT
    _footer_note(ws, 2, last, printed_on)

    # 2. Proyek (dengan laba per proyek) ------------------------------------
    ws = wb.create_sheet("Proyek")
    ws.sheet_properties.tabColor = "16A34A"
    _letterhead(ws, 9, "LAPORAN PROYEK DAN LABA PER PROYEK", label)
    rows, t_nilai, t_keluar = [], 0, 0
    for p in sorted(projects, key=lambda x: x.tanggal):
        keluar = project_expenses.get(p.id_proyek, 0)
        laba = p.nilai_proyek - keluar
        rows.append([
            p.id_proyek, p.tanggal, p.nama_klien, p.pekerjaan, p.nilai_proyek, keluar, laba,
            laba / p.nilai_proyek if p.nilai_proyek > 0 else "-", p.status_bayar,
        ])
        t_nilai += p.nilai_proyek
        t_keluar += keluar
    last = _table(
        ws, ["No. Invoice", "Tanggal", "Klien", "Pekerjaan", "Nilai Proyek",
             "Pengeluaran", "Laba Bersih", "Margin", "Status"],
        rows, [16, 13, 22, 34, 18, 18, 18, 10, 11],
        money=(5, 6), profit=(7,), pct=(8,), dates=(2,), center=(9,),
        total=["", "", "", "Total", t_nilai, t_keluar, t_nilai - t_keluar, "", ""] if rows else None,
    )
    _status_fill(ws, 9, HEADER_ROW + 1, HEADER_ROW + len(rows))
    _footer_note(ws, 9, last, printed_on)

    # 3. Pengeluaran ---------------------------------------------------------
    ws = wb.create_sheet("Pengeluaran")
    ws.sheet_properties.tabColor = "E11D48"
    _letterhead(ws, 6, "LAPORAN PENGELUARAN", label)
    rows = [
        [e.id_pengeluaran, e.tanggal, CATEGORY_LABELS.get(e.kategori, e.kategori),
         e.keterangan, e.id_proyek or "Umum", e.nominal]
        for e in sorted(expenses, key=lambda x: x.tanggal)
    ]
    last = _table(
        ws, ["ID", "Tanggal", "Kategori", "Keterangan", "Proyek", "Nominal"],
        rows, [16, 13, 18, 40, 18, 18], money=(6,), dates=(2,),
        total=["", "", "", "", "Total", sum(e.nominal for e in expenses)] if rows else None,
    )
    _footer_note(ws, 6, last, printed_on)

    # 4. Piutang -------------------------------------------------------------
    ws = wb.create_sheet("Piutang")
    ws.sheet_properties.tabColor = "D97706"
    _letterhead(ws, 5, "DAFTAR PIUTANG BERJALAN", label)
    rows = [[r["id"], r["tanggal"], r["klien"], r["nilai"], r["sisa"]] for r in receivables]
    last = _table(
        ws, ["No. Invoice", "Tanggal", "Klien", "Nilai Proyek", "Sisa Tagihan"],
        rows, [16, 13, 26, 20, 20], money=(4, 5), dates=(2,),
        total=["", "", "Total Piutang", "", sum(r["sisa"] for r in receivables)] if rows else None,
    )
    _footer_note(ws, 5, last, printed_on)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
