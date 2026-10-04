# Panduan Integrasi Google Sheets

Panduan ini menyiapkan Google Sheets sebagai database aplikasi (PRD bagian 5 dan 6).
Langkah 1–5 dikerjakan **manual oleh Anda** di Google. Langkah 6 dan seterusnya adalah
pekerjaan kode (fase M0/M1).

## Ringkasan Alur

```
Google Cloud Project ─► aktifkan Sheets API ─► buat Service Account ─► unduh key JSON
         │
Spreadsheet DB_Agungjaya ─► set locale/timezone ─► Share (Editor) ke e-mail Service Account
         │
.env backend (SPREADSHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE) ─► skrip setup_sheet.py ─► spike
```

## 1. Buat Google Cloud Project & aktifkan API
1. Buka <https://console.cloud.google.com/> dan login dengan akun Google yang memiliki spreadsheet.
2. Buat project baru, mis. `agungjaya-dashboard`.
3. Menu **APIs & Services → Library**, cari **Google Sheets API**, klik **Enable**.
   (Drive API tidak diperlukan karena aplikasi membuka spreadsheet lewat ID.)

## 2. Buat Service Account & key
1. **IAM & Admin → Service Accounts → Create service account**, nama mis. `dashboard-backend`.
   Tidak perlu memberi role di level project.
2. Buka service account tersebut → tab **Keys → Add key → Create new key → JSON**.
3. Simpan file ke `be-dashboard/credentials/service-account.json`.
   Folder `credentials/` dan `service-account*.json` sudah masuk `.gitignore`. **Jangan pernah di-commit atau dikirim lewat chat.**
4. Catat alamat e-mail service account (`...@...iam.gserviceaccount.com`) untuk langkah 4.

## 3. Buat spreadsheet
1. Buat spreadsheet baru bernama **`DB_Agungjaya`**.
2. **File → Settings** (Setelan):
   - **Locale:** Indonesia
   - **Time zone:** (GMT+07:00) Jakarta
   Ini mencegah `03/10/2026` dibaca sebagai 10 Maret (PRD risiko R6).
3. Salin **Spreadsheet ID** dari URL:
   `https://docs.google.com/spreadsheets/d/`**`<SPREADSHEET_ID>`**`/edit`

## 4. Bagikan ke Service Account
Klik **Share**, tempel e-mail service account, beri peran **Editor**, hilangkan centang "Notify".
Tanpa langkah ini backend akan mendapat error `403` / `PermissionError`.

## 5. Isi `.env`
```env
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service-account.json
SPREADSHEET_ID=<SPREADSHEET_ID>
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
```

## 6. Skrip setup tab (kode, fase M0)
`scripts/setup_sheet.py` (belum dibuat) bersifat **idempotent** dan akan membuat:
- 4 tab: `PEMASUKAN_PROYEK`, `PEMBAYARAN`, `PENGELUARAN`, `REKAP_DASHBOARD`
- header baris 1 + freeze row
- dropdown validasi untuk `tipe` dan `kategori`
- format angka untuk kolom uang
- `ARRAYFORMULA` untuk kolom turunan (`total_dibayar`, `sisa_piutang`, `status_bayar`)

Skema kolom ada di PRD bagian 5.2–5.5.

## 7. Spike verifikasi (wajib sebelum menulis repository)
Jalankan terhadap spreadsheet **uji**, bukan data asli. Catat hasilnya di PRD (risiko R7).

| # | Pertanyaan | Cara uji | Bila gagal |
| :---- | :---- | :---- | :---- |
| S1 | Apakah satu `spreadsheets.batchUpdate` dengan dua `appendCells` (proyek + pembayaran) benar-benar atomic? | Kirim request dengan request kedua yang sengaja tidak valid, pastikan request pertama tidak tertulis | Tulis pembayaran lebih dulu, dan rancang pemulihan (cek konsistensi saat refresh snapshot) |
| S2 | Apakah `append` ke `A:J` aman bersama `ARRAYFORMULA` di kolom K–M? | Append beberapa baris, cek rumus tidak rusak dan baris baru tidak terlewat | Backend tidak bergantung pada kolom turunan; rumus hanya untuk tampilan |
| S3 | Apakah penulisan `RAW` menyimpan tanggal ISO dan angka tepat seperti dikirim? | Tulis `2026-10-03` dan `21000000`, baca balik | Sesuaikan `valueInputOption` / format kolom |
| S4 | Berapa latensi satu `batchGet` 4 tab pada ±1.000 baris? | Ukur beberapa kali | Naikkan TTL / kurangi rentang baca |
| S5 | Bagaimana perilaku saat kena `429`? | Simulasikan burst request | Sesuaikan backoff |

## 8. Pola akses dari kode (acuan awal)
Nama fungsi di bawah adalah rencana dan **harus diverifikasi terhadap versi `gspread` yang terpasang saat spike**.

```python
import gspread

gc = gspread.service_account(filename=settings.GOOGLE_SERVICE_ACCOUNT_FILE)
sh = gc.open_by_key(settings.SPREADSHEET_ID)

# Baca: satu panggilan untuk beberapa tab (untuk snapshot)
result = sh.values_batch_get(ranges=["PEMASUKAN_PROYEK!A2:J", "PEMBAYARAN!A2:G", "PENGELUARAN!A2:G"])

# Tulis atomic lintas tab: spreadsheets.batchUpdate dengan appendCells
sh.batch_update({"requests": [ ... ]})
```

Prinsip: hanya `repositories/sheets_repository.py` yang mengimpor `gspread`. Service dan router tidak mengenal Sheets.

## 9. Troubleshooting

| Gejala | Penyebab umum | Solusi |
| :---- | :---- | :---- |
| `403 The caller does not have permission` | Spreadsheet belum dibagikan ke Service Account | Ulangi langkah 4 (peran Editor) |
| `404 Requested entity was not found` | `SPREADSHEET_ID` salah | Salin ulang ID dari URL |
| `403 Google Sheets API has not been used...` | API belum diaktifkan | Ulangi langkah 1.3 |
| `FileNotFoundError` pada key | Path `GOOGLE_SERVICE_ACCOUNT_FILE` salah (relatif terhadap folder tempat server dijalankan) | Jalankan dari `be-dashboard/` atau pakai path absolut |
| `429 Quota exceeded` | Terlalu banyak request | Pastikan semua baca lewat snapshot, jangan baca per request |
| Tanggal/angka terbaca aneh | Locale spreadsheet bukan Indonesia | Ulangi langkah 3.2 |

## 10. Keamanan
- Key service account setara kata sandi. Simpan di luar repo atau di secret manager pada produksi.
- Beri akses **hanya** ke satu spreadsheet ini, bukan ke seluruh Drive.
- Jika key bocor: hapus key di Cloud Console (Keys → Delete) lalu buat yang baru.
