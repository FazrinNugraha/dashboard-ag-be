"""Pembuat PDF laporan keuangan bergaya surat resmi (kop surat perusahaan).

Tata letak mengikuti dokumen resmi Agung Jaya Aluminium:
kop tengah + garis navy, judul, kotak info, bagian bernomor dengan tabel
header navy & baris belang, catatan, penutup, dan tanda tangan di kanan.

Semua teks identitas perusahaan ada di `COMPANY` agar mudah diganti tanpa
menyentuh logika tata letak.
"""
import io
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.domain import Expense, Project

# --- Identitas perusahaan (ubah di sini bila ada perubahan) -----------------
COMPANY = {
    "name": "AGUNG JAYA ALUMINIUM",
    "short_name": "Agung Jaya Aluminium",
    "tagline": "Jasa Pemasangan Kusen, Jendela & Pintu Aluminium \u2014 Kaca",
    "address": "Duren Sawit, Jakarta Timur",
    "city": "Jakarta Timur",
}

# --- Palet warna ------------------------------------------------------------
NAVY = colors.HexColor("#1E3A5F")      # kop, header tabel, judul bagian
BAND = colors.HexColor("#DCE6F1")      # baris belang
SUBTOTAL_BG = colors.HexColor("#EEF2F7")
LOSS_RED = colors.HexColor("#B91C1C")  # laba negatif
GREEN = colors.HexColor("#166534")     # laba positif

FONT = "Times-Roman"
FONT_BOLD = "Times-Bold"
FONT_ITALIC = "Times-Italic"

_MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

CATEGORY_LABELS = {
    "BAHAN_BAKU": "Bahan Baku",
    "AKSESORIS": "Aksesoris",
    "UPAH": "Upah Tukang",
    "OPERASIONAL": "Operasional",
    "LAINNYA": "Lain-lain",
}


# --- Format teks ------------------------------------------------------------
def rupiah(value: int) -> str:
    """1750000 -> 'Rp 1.750.000'; negatif -> '-Rp 500.000'."""
    sign = "-" if value < 0 else ""
    return f"{sign}Rp {abs(value):,}".replace(",", ".")


def format_date(d: date) -> str:
    """date(2026, 10, 14) -> '14 Oktober 2026'."""
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def period_label(period_type: str, period_value: str) -> str:
    """('month','2026-10') -> 'Oktober 2026'; ('year','2026') -> 'Tahun 2026'."""
    if period_type == "year":
        return f"Tahun {period_value}"
    year, month = period_value.split("-")
    return f"{_MONTHS[int(month) - 1]} {year}"


# --- Gaya paragraf ----------------------------------------------------------
def _style(name: str, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=kw.pop("fontName", FONT), **kw)


S_NAME = _style("name", fontName=FONT_BOLD, fontSize=17, textColor=NAVY, alignment=TA_CENTER, leading=20)
S_TAG = _style("tag", fontName=FONT_ITALIC, fontSize=8.5, alignment=TA_CENTER, leading=11)
S_ADDR = _style("addr", fontSize=8.5, alignment=TA_CENTER, leading=11)
S_TITLE = _style("title", fontName=FONT_BOLD, fontSize=13, alignment=TA_CENTER, leading=16)
S_BODY = _style("body", fontSize=9.5, leading=13, alignment=TA_JUSTIFY)
S_HEAD = _style("head", fontName=FONT_BOLD, fontSize=11, textColor=NAVY, leading=14, spaceBefore=10, spaceAfter=5)
S_CELL = _style("cell", fontSize=8.5, leading=10.5)
S_CELL_R = _style("cell_r", fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
S_CELL_B = _style("cell_b", fontName=FONT_BOLD, fontSize=8.5, leading=10.5)
S_CELL_BR = _style("cell_br", fontName=FONT_BOLD, fontSize=8.5, leading=10.5, alignment=TA_RIGHT)
S_NOTE = _style("note", fontSize=9, leading=12, leftIndent=10, bulletIndent=0)
S_SIGN = _style("sign", fontSize=9.5, leading=13, alignment=TA_RIGHT)
S_SIGN_B = _style("sign_b", fontName=FONT_BOLD, fontSize=9.5, leading=13, alignment=TA_RIGHT)


# --- Komponen tata letak ----------------------------------------------------
def _letterhead() -> list:
    """Kop surat: nama, tagline, alamat, lalu garis navy."""
    return [
        Paragraph(COMPANY["name"], S_NAME),
        Paragraph(COMPANY["tagline"], S_TAG),
        Paragraph(COMPANY["address"], S_ADDR),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=10),
    ]


def _info_box(rows: List[tuple], width: float) -> Table:
    """Kotak info 2 kolom (label tebal | isi), mis. Periode / Perihal."""
    data = [[Paragraph(k, S_CELL_B), Paragraph(v, S_CELL)] for k, v in rows]
    table = Table(data, colWidths=[width * 0.22, width * 0.78])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _data_table(header: List[str], rows: List[list], widths: List[float],
                right_cols: List[int], subtotal: Optional[list] = None,
                color_col: Optional[int] = None) -> Table:
    """Tabel standar: header navy, baris belang, subtotal tebal.

    right_cols: indeks kolom angka (rata kanan).
    color_col : kolom laba; teks diwarnai hijau/merah sesuai tandanya.
    """
    def cell(text, col, bold=False):
        right = col in right_cols
        style = (S_CELL_BR if right else S_CELL_B) if bold else (S_CELL_R if right else S_CELL)
        return Paragraph(str(text), style)

    head_style = ParagraphStyle("th", parent=S_CELL_B, textColor=colors.white)
    head_style_r = ParagraphStyle("thr", parent=S_CELL_BR, textColor=colors.white)
    data = [[Paragraph(h, head_style_r if i in right_cols else head_style) for i, h in enumerate(header)]]
    data += [[cell(v, i) for i, v in enumerate(r)] for r in rows]
    if subtotal:
        data.append([cell(v, i, bold=True) for i, v in enumerate(subtotal)])

    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    body_end = len(data) - (1 if subtotal else 0)
    for i in range(1, body_end):
        if i % 2 == 0:  # baris genap berwarna agar mudah dibaca
            style.append(("BACKGROUND", (0, i), (-1, i), BAND))
    if subtotal:
        style.append(("BACKGROUND", (0, -1), (-1, -1), SUBTOTAL_BG))
    table.setStyle(TableStyle(style))
    return table


def _profit_text(value: int) -> str:
    """Teks laba berwarna: hijau untung, merah rugi."""
    color = LOSS_RED if value < 0 else GREEN
    return f'<font color="{color.hexval().replace("0x", "#")}">{rupiah(value)}</font>'


class _NumberedCanvas(rl_canvas.Canvas):
    """Canvas yang menulis footer 'Halaman X dari Y' di tiap halaman."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages: list = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        width, _ = A4
        self.setStrokeColor(NAVY)
        self.setLineWidth(0.6)
        self.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
        self.setFont(FONT_ITALIC, 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(18 * mm, 10.5 * mm, f"{COMPANY['short_name']} \u2014 Laporan Keuangan")
        self.drawRightString(width - 18 * mm, 10.5 * mm, f"Halaman {self._pageNumber} dari {total}")


# --- Pembuat utama ----------------------------------------------------------
def build_report_pdf(
    kpi: dict,
    projects: List[Project],
    expenses: List[Expense],
    receivables: List[dict],
    label: str,
    printed_on: date,
    project_expenses: Optional[Dict[str, int]] = None,
) -> bytes:
    """Bangun PDF laporan.

    label            : periode yang tampil, mis. 'Oktober 2026'.
    project_expenses : total pengeluaran SEMUA waktu per id_proyek. Dipakai untuk
                       laba per proyek (agar benar walau pengeluaran proyek jatuh
                       di bulan lain). Bila None, dihitung dari `expenses` periode.
    """
    if project_expenses is None:
        project_expenses = defaultdict(int)
        for e in expenses:
            if e.id_proyek:
                project_expenses[e.id_proyek] += e.nominal

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=22 * mm,
        title=f"Laporan Keuangan {label}", author=COMPANY["short_name"],
    )
    width = doc.width
    el: list = []

    # Kop + judul + kotak info
    el += _letterhead()
    el += [Paragraph("LAPORAN KEUANGAN", S_TITLE), Spacer(1, 8)]
    el += [
        _info_box([
            ("Periode", label),
            ("Perihal", "Laporan Keuangan dan Laba per Proyek"),
            ("Dicetak", format_date(printed_on)),
        ], width),
        Spacer(1, 8),
        Paragraph(
            f"Berikut kami sampaikan laporan keuangan {COMPANY['short_name']} untuk periode "
            f"<b>{label}</b>, meliputi ringkasan keuangan, laba per proyek, rincian pengeluaran, "
            "dan daftar piutang yang masih berjalan.", S_BODY),
    ]

    # 1. Ringkasan keuangan
    omzet = kpi["omzet"]["value"]
    kas = kpi["kas_masuk"]["value"]
    keluar = kpi["pengeluaran"]["value"]
    laba = kpi["laba_bersih"]["value"]
    margin = kpi["laba_bersih"].get("margin_pct")
    el.append(Paragraph("1. Ringkasan Keuangan", S_HEAD))
    el.append(_data_table(
        ["Keterangan", "Nilai"],
        [
            ["Omzet (nilai invoice terbit)", rupiah(omzet)],
            ["Kas Masuk (pembayaran diterima)", rupiah(kas)],
            ["Total Pengeluaran", rupiah(keluar)],
            ["Margin Laba", f"{margin}%" if margin is not None else "-"],
        ],
        [width * 0.65, width * 0.35], right_cols=[1],
        subtotal=["Laba Bersih (Kas Masuk \u2212 Pengeluaran)", _profit_text(laba)],
    ))

    # 2. Laba per proyek
    el.append(Paragraph("2. Laba per Proyek", S_HEAD))
    if projects:
        rows, t_nilai, t_keluar = [], 0, 0
        for no, p in enumerate(sorted(projects, key=lambda x: x.tanggal), 1):
            keluar_p = project_expenses.get(p.id_proyek, 0)
            laba_p = p.nilai_proyek - keluar_p
            margin_p = f"{laba_p / p.nilai_proyek * 100:.1f}%" if p.nilai_proyek > 0 else "-"
            rows.append([no, p.id_proyek, p.nama_klien, rupiah(p.nilai_proyek),
                         rupiah(keluar_p), _profit_text(laba_p), margin_p])
            t_nilai += p.nilai_proyek
            t_keluar += keluar_p
        el.append(_data_table(
            ["No", "No. Invoice", "Klien", "Nilai Proyek", "Pengeluaran", "Laba Bersih", "Margin"],
            rows,
            [width * w for w in (0.06, 0.17, 0.19, 0.16, 0.16, 0.17, 0.09)],
            right_cols=[3, 4, 5, 6],
            subtotal=["", "", "Total", rupiah(t_nilai), rupiah(t_keluar),
                      _profit_text(t_nilai - t_keluar), ""],
        ))
    else:
        el.append(Paragraph("Tidak ada proyek pada periode ini.", S_BODY))

    # 3. Rincian pengeluaran per kategori
    el.append(Paragraph("3. Rincian Pengeluaran", S_HEAD))
    if expenses:
        per_cat: Dict[str, int] = defaultdict(int)
        for e in expenses:
            per_cat[e.kategori] += e.nominal
        total_proyek = sum(e.nominal for e in expenses if e.id_proyek)
        rows = [[CATEGORY_LABELS.get(k, k), rupiah(v)] for k, v in sorted(per_cat.items(), key=lambda x: -x[1])]
        el.append(_data_table(
            ["Kategori", "Nominal"], rows, [width * 0.65, width * 0.35], right_cols=[1],
            subtotal=["Total Pengeluaran", rupiah(sum(per_cat.values()))],
        ))
        el.append(Spacer(1, 4))
        el.append(Paragraph(
            f"Dari total tersebut, <b>{rupiah(total_proyek)}</b> dibebankan ke proyek tertentu dan "
            f"<b>{rupiah(sum(per_cat.values()) - total_proyek)}</b> merupakan pengeluaran umum "
            "(mis. listrik, air, internet, upah umum).", S_BODY))
    else:
        el.append(Paragraph("Tidak ada pengeluaran pada periode ini.", S_BODY))

    # 4. Piutang berjalan
    el.append(Paragraph("4. Daftar Piutang Berjalan", S_HEAD))
    if receivables:
        rows = [[no, r["id"], r["klien"], format_date(r["tanggal"]), rupiah(r["nilai"]), rupiah(r["sisa"])]
                for no, r in enumerate(receivables, 1)]
        el.append(_data_table(
            ["No", "No. Invoice", "Klien", "Tanggal", "Nilai Proyek", "Sisa Tagihan"],
            rows,
            [width * w for w in (0.06, 0.18, 0.21, 0.19, 0.18, 0.18)],
            right_cols=[4, 5],
            subtotal=["", "", "", "Total Piutang", "", rupiah(sum(r["sisa"] for r in receivables))],
        ))
    else:
        el.append(Paragraph("Tidak ada piutang saat ini.", S_BODY))

    # Catatan + penutup + tanda tangan (dijaga tetap satu blok)
    notes = [
        "Omzet dihitung dari tanggal invoice; Kas Masuk dari tanggal pembayaran diterima.",
        "Laba Bersih bulanan berbasis kas: Kas Masuk dikurangi Total Pengeluaran.",
        "Laba per proyek = Nilai Proyek dikurangi pengeluaran proyek tersebut "
        "(seluruh pengeluaran yang dicatat untuk proyek itu).",
        "Daftar piutang menampilkan seluruh sisa tagihan saat ini, tidak dibatasi periode.",
    ]
    closing = [Paragraph("Catatan", S_HEAD)]
    closing += [Paragraph(n, S_NOTE, bulletText="\u2022") for n in notes]
    closing += [
        Spacer(1, 8),
        Paragraph(
            "Demikian laporan keuangan ini kami sampaikan sebagai bahan evaluasi dan pengambilan "
            "keputusan usaha. Atas perhatiannya, kami ucapkan terima kasih.", S_BODY),
        Spacer(1, 14),
        Paragraph(f"{COMPANY['city']}, {format_date(printed_on)}", S_SIGN),
        Paragraph("Hormat kami,", S_SIGN),
        Spacer(1, 40),
        Paragraph(COMPANY["short_name"], S_SIGN_B),
    ]
    el.append(KeepTogether(closing))

    doc.build(el, canvasmaker=_NumberedCanvas)
    return out.getvalue()
