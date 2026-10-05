from typing import Protocol, List, Dict
import gspread_asyncio
import gspread
import logging
from app.schemas.domain import Project, Payment, Expense

logger = logging.getLogger(__name__)

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
            values = await sh.values_batch_get(ranges)
        except Exception as e:
            logger.error(f"Failed to read from Google Sheets: {e}")
            raise Exception("SHEETS_UNAVAILABLE")

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
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)

        ws_proyek = await sh.worksheet("PEMASUKAN_PROYEK")

        # Hitung baris log: baris baru = setelah baris data terakhir yang terisi
        rows_before = await ws_proyek.get_values("A2:A")
        filled_count = len([r for r in rows_before if r and r[0]])
        new_row_number = 2 + filled_count  # A2 adalah data pertama

        proj_values = [
            project.id_proyek, project.tanggal.isoformat(), project.nama_klien,
            project.alamat, project.pekerjaan, project.subtotal, project.diskon,
            project.nilai_proyek, project.bulan_filter, project.dibuat_oleh
        ]

        # append_row kadang overwrite baris terakhir, jadi kita update range spesifik
        try:
            await ws_proyek.update(
                range_name=f'A{new_row_number}:J{new_row_number}',
                values=[[str(v) if isinstance(v, str) else v for v in proj_values]],
                value_input_option="RAW",
            )
            logger.info(f"Proyek {project.id_proyek} ditulis di baris {new_row_number} PEMASUKAN_PROYEK")
        except Exception as e:
            logger.error(f"Failed to append project row: {e}")
            raise Exception("SHEETS_UNAVAILABLE")

        # Tulis formula K-L-M (total_dibayar, sisa_piutang, status_bayar)
        # persis di baris yang baru dibuat agar kolom tidak kosong.
        try:
            formulas = [[
                f'=SUMIF(PEMBAYARAN!B:B; A{new_row_number}; PEMBAYARAN!D:D)',
                f'=H{new_row_number} - K{new_row_number}',
                f'=IF(L{new_row_number}<=0; "LUNAS"; "DP")',
            ]]
            await ws_proyek.update(
                range_name=f'K{new_row_number}:M{new_row_number}',
                values=formulas,
                value_input_option='USER_ENTERED',
            )
            logger.info(f"Formula K-L-M ditulis di baris {new_row_number}")
        except Exception as e:
            logger.warning(f"Gagal menulis formula di baris {new_row_number}: {e}")

        if dp_payment:
            try:
                ws_bayar = await sh.worksheet("PEMBAYARAN")
                pay_values = [
                    dp_payment.id_bayar, dp_payment.id_proyek, dp_payment.tanggal.isoformat(),
                    dp_payment.nominal, dp_payment.tipe, dp_payment.bulan_filter, dp_payment.dicatat_oleh
                ]
                rows_bayar = await ws_bayar.get_values("A1:A")
                n_bayar = 1 + len([r for r in rows_bayar if r and r[0]])
                await ws_bayar.update(
                    range_name=f'A{n_bayar}:G{n_bayar}',
                    values=[[str(v) if isinstance(v, str) else v for v in pay_values]],
                    value_input_option="RAW",
                )
                logger.info(f"Pembayaran {dp_payment.id_bayar} ditulis di PEMBAYARAN")
            except Exception as e:
                logger.error(f"Failed to append payment row: {e}")
                raise Exception("SHEETS_UNAVAILABLE")

    async def write_payment(self, payment: Payment):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PEMBAYARAN")
        pay_values = [
            payment.id_bayar, payment.id_proyek, payment.tanggal.isoformat(),
            payment.nominal, payment.tipe, payment.bulan_filter, payment.dicatat_oleh
        ]
        rows_bayar = await ws.get_values("A1:A")
        n_bayar = 1 + len([r for r in rows_bayar if r and r[0]])
        await ws.update(
            range_name=f'A{n_bayar}:G{n_bayar}',
            values=[[str(v) if isinstance(v, str) else v for v in pay_values]],
            value_input_option="RAW"
        )

        # Sinkronkan kolom K-M (total dibayar, sisa, status) di baris proyek
        try:
            ws_proyek = await sh.worksheet("PEMASUKAN_PROYEK")
            ids = await ws_proyek.get_values("A2:A")
            for i, r in enumerate(ids):
                if r and r[0] == payment.id_proyek:
                    n = i + 2
                    await ws_proyek.update(
                        range_name=f'K{n}:M{n}',
                        values=[[
                            f'=SUMIF(PEMBAYARAN!B:B; A{n}; PEMBAYARAN!D:D)',
                            f'=H{n} - K{n}',
                            f'=IF(L{n}<=0; "LUNAS"; "DP")',
                        ]],
                        value_input_option='USER_ENTERED',
                    )
                    break
        except Exception as e:
            logger.warning(f"Gagal sinkron status proyek di sheet: {e}")

    async def write_expense(self, expense: Expense):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PENGELUARAN")
        exp_values = [
            expense.id_pengeluaran, expense.tanggal.isoformat(), expense.kategori,
            expense.keterangan, expense.nominal, expense.bulan_filter, expense.dibuat_oleh
        ]
        rows_exp = await ws.get_values("A1:A")
        n_exp = 1 + len([r for r in rows_exp if r and r[0]])
        await ws.update(
            range_name=f'A{n_exp}:G{n_exp}',
            values=[[str(v) if isinstance(v, str) else v for v in exp_values]],
            value_input_option="RAW"
        )
