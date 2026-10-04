from typing import Protocol, List, Dict
import gspread_asyncio
import gspread
import logging
from app.schemas.domain import Project, Payment, Expense

logger = logging.getLogger(__name__)

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
                        subtotal=int(row_padded[5]) if row_padded[5] else 0,
                        diskon=int(row_padded[6]) if row_padded[6] else 0,
                        nilai_proyek=int(row_padded[7]) if row_padded[7] else 0,
                        bulan_filter=row_padded[8],
                        dibuat_oleh=row_padded[9],
                        total_dibayar=int(row_padded[10]) if row_padded[10] else 0,
                        sisa_piutang=int(row_padded[11]) if row_padded[11] else 0,
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
                        nominal=int(row_padded[3]) if row_padded[3] else 0,
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
                        nominal=int(row_padded[4]) if row_padded[4] else 0,
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
        requests = []
        
        proj_values = [
            project.id_proyek, project.tanggal.isoformat(), project.nama_klien, 
            project.alamat, project.pekerjaan, project.subtotal, project.diskon, 
            project.nilai_proyek, project.bulan_filter, project.dibuat_oleh
        ]
        
        requests.append({
            "appendCells": {
                "sheetId": ws_proyek.id,
                "rows": [{"values": [{"userEnteredValue": {"stringValue": str(v)} if isinstance(v, str) else {"numberValue": v}} for v in proj_values]}],
                "fields": "userEnteredValue"
            }
        })
        
        if dp_payment:
            ws_bayar = await sh.worksheet("PEMBAYARAN")
            pay_values = [
                dp_payment.id_bayar, dp_payment.id_proyek, dp_payment.tanggal.isoformat(),
                dp_payment.nominal, dp_payment.tipe, dp_payment.bulan_filter, dp_payment.dicatat_oleh
            ]
            requests.append({
                "appendCells": {
                    "sheetId": ws_bayar.id,
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": str(v)} if isinstance(v, str) else {"numberValue": v}} for v in pay_values]}],
                    "fields": "userEnteredValue"
                }
            })
            
        try:
            await sh.batch_update({"requests": requests})
        except Exception as e:
            logger.error(f"Failed to batch_update project and payment: {e}")
            raise Exception("SHEETS_UNAVAILABLE")

    async def write_payment(self, payment: Payment):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PEMBAYARAN")
        pay_values = [
            payment.id_bayar, payment.id_proyek, payment.tanggal.isoformat(),
            payment.nominal, payment.tipe, payment.bulan_filter, payment.dicatat_oleh
        ]
        await ws.append_row(pay_values, value_input_option="RAW")

    async def write_expense(self, expense: Expense):
        client = await self.agcm.authorize()
        sh = await client.open_by_key(self.spreadsheet_id)
        ws = await sh.worksheet("PENGELUARAN")
        exp_values = [
            expense.id_pengeluaran, expense.tanggal.isoformat(), expense.kategori,
            expense.keterangan, expense.nominal, expense.bulan_filter, expense.dibuat_oleh
        ]
        await ws.append_row(exp_values, value_input_option="RAW")
