import gspread_asyncio
from google.oauth2.service_account import Credentials
from app.core.config import get_settings
from app.repositories.sheets_repository import GoogleSheetsRepository
from app.domain.snapshot import SnapshotCache

# Instantiate globals
_agcm = None
_repository = None
_snapshot_cache = None

def get_creds():
    settings = get_settings()
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=[
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
    )
    return creds

import asyncio
_write_lock = asyncio.Lock()

def get_write_lock() -> asyncio.Lock:
    return _write_lock

def get_repository() -> GoogleSheetsRepository:
    # Pastikan cache (dan repository) sudah diinisialisasi sebelum dipakai.
    get_snapshot_cache()
    return _repository

def get_snapshot_cache() -> SnapshotCache:
    global _agcm, _repository, _snapshot_cache
    if _snapshot_cache is None:
        settings = get_settings()
        _agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)
        _repository = GoogleSheetsRepository(_agcm, settings.SPREADSHEET_ID)
        _snapshot_cache = SnapshotCache(_repository, ttl_seconds=settings.CACHE_TTL_SECONDS)
    return _snapshot_cache
