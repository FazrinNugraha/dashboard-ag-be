import re
from typing import Protocol, List, Dict
import gspread_asyncio
import gspread
import logging
from app.core.errors import AppError
from app.core.retry import call_with_retry
from app.schemas.domain import Project, Payment, Expense

_SCIENTIFIC_RE = re.compile(r"^-?\d+(?:\.\d+)?[eE][+-]?\d+$")

logger = logging.getLogger(__name__)

# Penulisan tidak idempotent: hanya retry status yang pasti belum diproses.
WRITE_RETRY_STATUSES = {429, 503}


def _write_with_retry(factory):
    return call_with_retry(
        factory,
        retry_statuses=WRITE_RETRY_STATUSES,
        retry_network=False,
    )


# Formula kolom turunan K-L-M. Memakai ROW()/INDIRECT() agar tidak perlu tahu
# nomor baris saat append (appendCells atomic, tidak membaca kolom).
# Pemisah argumen ";" sesuai locale spreadsheet (id_ID -> ;).
_PROJECT_FORMULAS = (
    '=SUMIF(PEMBAYARAN!$B:$B;INDIRECT("A"&ROW());PEMBAYARAN!$D:$D)',
    '=INDIRECT("H"&ROW())-INDIRECT("K"&ROW())',
    '=IF(INDIRECT("L"&ROW())<=0;"LUNAS";"DP")',
)


def _cell(value):
    """Bentuk satu sel untuk batchUpdate (StringValue / NumberValue)."""
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def _formula(formula: str):
    return {"userEnteredValue": {"formulaValue": formula}}


def _project_row(project: Project) -> list:
    return [
        _cell(project.id_proyek),
        _cell(project.tanggal.isoformat()),
        _cell(project.nama_klien),
        _cell(project.alamat),
        _cell(project.pekerjaan),
        _cell(project.subtotal),
        _cell(project.diskon),
        _cell(project.nilai_proyek),
        _cell(project.bulan_filter),
        _cell(project.dibuat_oleh),
        _formula(_PROJECT_FORMULAS[0]),
        _formula(_PROJECT_FORMULAS[1]),
        _formula(_PROJECT_FORMULAS[2]),
    ]


def _payment_row(payment: Payment) -> list:
    return [
        _cell(payment.id_bayar),
        _cell(payment.id_proyek),
        _cell(payment.tanggal.isoformat()),
        _cell(payment.nominal),
        _cell(payment.tipe),
        _cell(payment.bulan_filter),
        _cell(payment.dicatat_oleh),
    ]


def _expense_row(expense: Expense) -> list:
    return [
        _cell(expense.id_pengeluaran),
        _cell(expense.tanggal.isoformat()),
        _cell(expense.kategori),
        _cell(expense.keterangan),
        _cell(expense.nominal),
        _cell(expense.bulan_filter),
        _cell(expense.dibuat_oleh),
    ]


def parse_int(v) -> int:
    """Parse angka dari Sheets dengan berbagai format.

    Menangani: integer/float, 'Rp 8.000.000', '8.000.000', '6,700,000',
    '3,000.000', notasi ilmiah '2.1E+07', dan campuran keduanya.
    """
    if v is None or v == '':
        return 0
    if isinstance(v, (int, float)):
        return int(v)

    s = str(v).strip().replace('Rp', '').replace(' ', '')
    if not s:
        return 0

    # Notasi ilmiah dari sel numerik besar -> pakai float.
    if _SCIENTIFIC_RE.match(s):
        try:
            return int(float(s))
        except ValueError:
            return 0

    # Normalisasi pemisah ribuan/desimal: buang titik & koma, jaga tanda minus.
    neg = s.startswith('-')
    digits = ''.join(ch for ch in s if ch.isdigit())
    n = int(digits) if digits else 0
    return -n if neg else n

def _parse_rows(values, index: int, width: int, factory, tab_name: str, stats: dict) -> list:
    """Parse baris satu tab memakai `factory`, catat jumlah sah/rusak.

    Baris kosong dilewati tanpa dihitung; baris yang gagal validasi dicatat
    sebagai `skipped` agar terlihat di GET /health/sheets.
    """
    parsed = []
    skipped = 0
    value_ranges = values.get("valueRanges", [])
    if index < len(value_ranges) and "values" in value_ranges[index]:
        for row in value_ranges[index]["values"]:
            if not row or not row[0]:
                continue
            try:
                row_padded = row + [''] * (width - len(row))
                parsed.append(factory(row_padded))
            except Exception as e:
                skipped += 1
                logger.warning("Skipping malformed %s row: %s. Error: %s", tab_name, row, e)
    stats[tab_name] = {"parsed": len(parsed), "skipped": skipped}
    return parsed


class SheetsRepositoryProtocol(Protocol):
    async def read_all(self) -> tuple[List[Project], List[Payment], List[Expense]]:
        """Reads all tabs in a single batchGet if possible, returning parsed models."""
        pass

    def last_read_stats(self) -> dict:
        """Statistik pembacaan terakhir (jumlah baris sah/dilewati per tab)."""
        pass
    async def write_project_and_dp(self, project: Project, dp_payment: Payment | None):
        pass
    async def write_payment(self, payment: Payment):
        pass
    async def write_expense(self, expense: Expense):
        pass

class GoogleSheetsRepository:
    def __init__(self, agcm: gspread_asyncio.AsyncioGspreadClientManager, spreadsheet_id: str):
        self.agcm = agcm
        self.spreadsheet_id = spreadsheet_id
        self._read_stats: dict = {}

    def last_read_stats(self) -> dict:
        return self._read_stats

    async def _get_worksheet(self, title: str):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        return await sh.worksheet(title)

    async def read_all(self) -> tuple[List[Project], List[Payment], List[Expense]]:
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        
        # We can use batch_get to get multiple ranges at once to save API calls
        ranges = ["PEMASUKAN_PROYEK!A2:M", "PEMBAYARAN!A2:G", "PENGELUARAN!A2:G"]
        
        try:
            values = await call_with_retry(lambda: sh.values_batch_get(ranges))
        except Exception as e:
            logger.error(f"Failed to read from Google Sheets: {e}")
            raise AppError("SHEETS_UNAVAILABLE", "Google Sheets tidak dapat dijangkau.", 503)

        stats: dict = {}

        projects = _parse_rows(
            values, 0, 13,
            lambda r: Project(
                id_proyek=r[0], tanggal=r[1], nama_klien=r[2], alamat=r[3],
                pekerjaan=r[4], subtotal=parse_int(r[5]), diskon=parse_int(r[6]),
                nilai_proyek=parse_int(r[7]), bulan_filter=r[8], dibuat_oleh=r[9],
                total_dibayar=parse_int(r[10]), sisa_piutang=parse_int(r[11]),
                status_bayar=r[12] if r[12] else "DP",
            ),
            "PEMASUKAN_PROYEK", stats,
        )
        payments = _parse_rows(
            values, 1, 7,
            lambda r: Payment(
                id_bayar=r[0], id_proyek=r[1], tanggal=r[2], nominal=parse_int(r[3]),
                tipe=r[4], bulan_filter=r[5], dicatat_oleh=r[6],
            ),
            "PEMBAYARAN", stats,
        )
        expenses = _parse_rows(
            values, 2, 7,
            lambda r: Expense(
                id_pengeluaran=r[0], tanggal=r[1], kategori=r[2], keterangan=r[3],
                nominal=parse_int(r[4]), bulan_filter=r[5], dibuat_oleh=r[6],
            ),
            "PENGELUARAN", stats,
        )

        self._read_stats = stats
        return projects, payments, expenses

    async def write_project_and_dp(self, project: Project, dp_payment: Payment | None):
        """Tulis proyek + DP dalam satu batchUpdate atomic (all-or-nothing).

        Memakai appendCells sehingga Google yang menentukan baris berikutnya
        (aman terhadap baris kosong, tanpa membaca kolom). Formula K-L-M
        disertakan pada baris yang sama via ROW()/INDIRECT().
        """
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)

        ws_proyek = await sh.worksheet("PEMASUKAN_PROYEK")
        requests = [
            {
                "appendCells": {
                    "sheetId": ws_proyek.id,
                    "fields": "*",
                    "rows": [{"values": _project_row(project)}],
                }
            }
        ]

        if dp_payment:
            ws_bayar = await sh.worksheet("PEMBAYARAN")
            requests.append(
                {
                    "appendCells": {
                        "sheetId": ws_bayar.id,
                        "fields": "*",
                        "rows": [{"values": _payment_row(dp_payment)}],
                    }
                }
            )

        try:
            await _write_with_retry(lambda: sh.batch_update({"requests": requests}))
            logger.info(
                "Proyek %s + %s ditulis atomic via appendCells",
                project.id_proyek,
                f"DP {dp_payment.id_bayar}" if dp_payment else "tanpa DP",
            )
        except Exception as e:
            logger.error("Gagal menulis proyek/pembayaran: %s", e)
            raise AppError("SHEETS_UNAVAILABLE", "Gagal menyimpan ke Google Sheets.", 503)

    async def write_payment(self, payment: Payment):
        """Append 1 baris pembayaran. Kolom K-M proyek dihitung ulang otomatis
        oleh formula SUMIF (ROW/INDIRECT), jadi tidak perlu sinkronisasi manual."""
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PEMBAYARAN")
        try:
            await _write_with_retry(
                lambda: sh.batch_update(
                    {
                        "requests": [
                            {
                                "appendCells": {
                                    "sheetId": ws.id,
                                    "fields": "*",
                                    "rows": [{"values": _payment_row(payment)}],
                                }
                            }
                        ]
                    }
                )
            )
            logger.info("Pembayaran %s ditulis via appendCells", payment.id_bayar)
        except Exception as e:
            logger.error("Gagal menulis pembayaran: %s", e)
            raise AppError("SHEETS_UNAVAILABLE", "Gagal menyimpan ke Google Sheets.", 503)

    async def write_expense(self, expense: Expense):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PENGELUARAN")
        try:
            await _write_with_retry(
                lambda: sh.batch_update(
                    {
                        "requests": [
                            {
                                "appendCells": {
                                    "sheetId": ws.id,
                                    "fields": "*",
                                    "rows": [{"values": _expense_row(expense)}],
                                }
                            }
                        ]
                    }
                )
            )
            logger.info("Pengeluaran %s ditulis via appendCells", expense.id_pengeluaran)
        except Exception as e:
            logger.error("Gagal menulis pengeluaran: %s", e)
            raise AppError("SHEETS_UNAVAILABLE", "Gagal menyimpan ke Google Sheets.", 503)
