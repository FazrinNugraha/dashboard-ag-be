import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Check for gspread async
try:
    import gspread_asyncio
    from google.oauth2.service_account import Credentials
except ImportError:
    print("Please install gspread-asyncio and google-auth: pip install gspread-asyncio google-auth")
    sys.exit(1)

def get_creds():
    # To obtain service account credentials
    creds = Credentials.from_service_account_file(
        'credentials.json',
        scopes=[
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
    )
    return creds

async def main():
    SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    if not SPREADSHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID is not set in .env")
        sys.exit(1)
        
    if not os.path.exists("credentials.json"):
        print("ERROR: credentials.json not found in the root directory")
        sys.exit(1)

    print("Authenticating with Google Sheets...")
    agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
    client = await agcm.authorize()

    print(f"Opening spreadsheet: {SPREADSHEET_ID}")
    try:
        sh = await client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        print(f"Failed to open spreadsheet: {e}")
        print("Make sure the Service Account email is added as an Editor to the Google Sheet.")
        sys.exit(1)

    TABS = {
        "PEMASUKAN_PROYEK": [
            "id_proyek", "tanggal", "nama_klien", "alamat", "pekerjaan", 
            "subtotal", "diskon", "nilai_proyek", "bulan_filter", "dibuat_oleh", 
            "total_dibayar", "sisa_piutang", "status_bayar"
        ],
        "PEMBAYARAN": [
            "id_bayar", "id_proyek", "tanggal", "nominal", "tipe", "bulan_filter", "dicatat_oleh"
        ],
        "PENGELUARAN": [
            "id_pengeluaran", "tanggal", "kategori", "keterangan", "nominal", "bulan_filter", "dibuat_oleh"
        ],
        "REKAP_DASHBOARD": [
            "Bulan", "Omzet", "Kas Masuk", "Piutang", "Pengeluaran", "Laba Bersih"
        ]
    }

    # Iterate through tabs and create/update them
    for tab_name, headers in TABS.items():
        try:
            worksheet = await sh.worksheet(tab_name)
            print(f"Tab '{tab_name}' already exists.")
        except Exception:
            print(f"Creating tab '{tab_name}'...")
            worksheet = await sh.add_worksheet(title=tab_name, rows=1000, cols=20)
        
        # Setup headers in row 1
        print(f"Setting headers for '{tab_name}'...")
        # Since gspread_asyncio uses 1-based indexing for rows/cols in some functions,
        # but batch_update is preferred for performance.
        # Let's use simple append or range update for headers.
        cell_list = await worksheet.range(1, 1, 1, len(headers))
        for i, cell in enumerate(cell_list):
            cell.value = headers[i]
        await worksheet.update_cells(cell_list)
        
        # Formatting headers (bold)
        await worksheet.format('A1:Z1', {'textFormat': {'bold': True}})

    print("Spreadsheet setup completed successfully!")

if __name__ == '__main__':
    asyncio.run(main())
