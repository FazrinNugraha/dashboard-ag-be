from typing import Protocol, List, Dict
import gspread_asyncio
import gspread
import logging
from app.core.errors import AppError
from app.core.retry import call_with_retry
from app.schemas.domain import Project, Payment, Expense

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
    """Parse angka dari Sheets, mis. '8.000.000', 'Rp 8.000.000', 8000000."""
    if v is None or v == '':
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace('Rp', '').replace(' ', '')
    neg = s.startswith('-')
    digits = ''.join(ch for ch in s.split(',')[0] if ch.isdigit())
    n = int(digits) if digits else 0
    return -n if neg else n

class SheetsRepositoryProtocol(Protocol):
    async def read_all(self) -> tuple[List[Project], List[Payment], List[Expense]]:
        """Reads all tabs in a single batchGet if possible, returning parsed models."""
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

        projects = []
        payments = []
        expenses = []

        # Parse Projects (values[0]['values'])
        if 'values' in values['valueRanges'][0]:
            for row in values['valueRanges'][0]['values']:
                if not row or not row[0]: # Skip empty rows
                    continue
                try:
                    # Pad row if some trailing columns are empty
                    row_padded = row + [''] * (13 - len(row))
                    projects.append(Project(
                        id_proyek=row_padded[0],
                        tanggal=row_padded[1],
                        nama_klien=row_padded[2],
                        alamat=row_padded[3],
                        pekerjaan=row_padded[4],
                        subtotal=parse_int(row_padded[5]),
                        diskon=parse_int(row_padded[6]),
                        nilai_proyek=parse_int(row_padded[7]),
                        bulan_filter=row_padded[8],
                        dibuat_oleh=row_padded[9],
                        total_dibayar=parse_int(row_padded[10]),
                        sisa_piutang=parse_int(row_padded[11]),
                        status_bayar=row_padded[12] if row_padded[12] else "DP"
                    ))
                except Exception as e:
                    logger.warning(f"Skipping malformed project row: {row}. Error: {e}")

        # Parse Payments (values[1]['values'])
        if 'values' in values['valueRanges'][1]:
            for row in values['valueRanges'][1]['values']:
                if not row or not row[0]:
                    continue
                try:
                    row_padded = row + [''] * (7 - len(row))
                    payments.append(Payment(
                        id_bayar=row_padded[0],
                        id_proyek=row_padded[1],
                        tanggal=row_padded[2],
                        nominal=parse_int(row_padded[3]),
                        tipe=row_padded[4],
                        bulan_filter=row_padded[5],
                        dicatat_oleh=row_padded[6]
                    ))
                except Exception as e:
                    logger.warning(f"Skipping malformed payment row: {row}. Error: {e}")

        # Parse Expenses (values[2]['values'])
        if 'values' in values['valueRanges'][2]:
            for row in values['valueRanges'][2]['values']:
                if not row or not row[0]:
                    continue
                try:
                    row_padded = row + [''] * (7 - len(row))
                    expenses.append(Expense(
                        id_pengeluaran=row_padded[0],
                        tanggal=row_padded[1],
                        kategori=row_padded[2],
                        keterangan=row_padded[3],
                        nominal=parse_int(row_padded[4]),
                        bulan_filter=row_padded[5],
                        dibuat_oleh=row_padded[6]
                    ))
                except Exception as e:
                    logger.warning(f"Skipping malformed expense row: {row}. Error: {e}")

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
