# Backend Dashboard (FastAPI)

Backend dashboard keuangan AGUNGJAYA ALUMINIUM. Spesifikasi lengkap: [docs/PRD_Dashboard_Agungjaya_Aluminium.md](docs/PRD_Dashboard_Agungjaya_Aluminium.md).
Integrasi Google Sheets: [docs/PANDUAN_INTEGRASI_GOOGLE_SHEETS.md](docs/PANDUAN_INTEGRASI_GOOGLE_SHEETS.md).

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

Copy-Item .env.example .env
python -c "import secrets;print(secrets.token_urlsafe(48))"   # isi JWT_SECRET
python scripts/hash_password.py                                # isi ADMIN1_PASSWORD_HASH / ADMIN2_PASSWORD_HASH
```

## Menjalankan

```powershell
uvicorn app.main:app --reload --port 8000
```

Dokumentasi interaktif (hanya `ENV` selain production): `http://localhost:8000/docs`.
Jalankan **1 worker** saja (lihat PRD 6.5).

## Tes

```powershell
pytest
```

## Struktur

```
app/
├─ main.py              # app factory, CORS, request id, error handler
├─ core/                # config, errors, security (JWT/bcrypt), rate_limit
├─ api/v1/              # auth, invoices, system, router
├─ schemas/             # model Pydantic
└─ parsers/             # invoice_parser (fungsi murni)
scripts/hash_password.py
tests/
```
