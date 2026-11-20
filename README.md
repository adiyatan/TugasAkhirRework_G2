# Dompet & Akun SOP — PT Lokal Komoditi Indonesia

Sistem pencatatan transaksi keuangan, ekstraksi rekening koran PDF, dan rekonsiliasi kas/bank berbasis **FastAPI**, **SQLite**, **Tailwind CSS + Vanilla ES Modules**, **PyMuPDF**, dan **Vision AI (LiteLLM)**.

---

## Ringkasan Modul & Status Implementasi

| Menu | Route API | Status | Ringkasan Fitur |
| :--- | :--- | :--- | :--- |
| **Input Struk** | `/api/v1/struk/*` | **Aktif** | Upload bukti multi-slot (`Normal`, `Transfer Flip`, `Slip Gaji`, `Reimburse`, & `Kas Operasional`), ekstraksi Vision AI, validasi aturan SOP, anti-duplikat SHA-256, edit/hapus riwayat, dan auto-rekonsiliasi. |
| **Input Mutasi Bank** | `/api/v1/mutasi/*` | **Aktif** | Upload PDF rekening koran dengan **2 jalur ekstraksi**: parser **deterministik (0 token AI)** untuk teks PDF BRI IBBIZ, dan **Vision AI per halaman (2.0x PNG)** untuk PDF kurva vektor/scan (BNI Wondr, Bank Jago, BRI Operasional). Dilengkapi cek keseimbangan saldo, modal edit baris preview, anti-double (`file_hash` + `dedup_signature`), riwayat batch, dan auto-rekonsiliasi. |
| **Rekonsiliasi** | `/api/v1/rekonsiliasi` | **Backend Ready / UI Placeholder** | Mesin auto-matching (`EXACT`, `TOLERANCE`, `PINDAH_BUKU_PAIR`) di `rekonsiliasi_service.py` aktif otomatis saat simpan struk & mutasi; UI manual matching & ekspor Cash Report sedang disiapkan. |
| **Home** | `/api/v1/home` | **Aktif** | Menampilkan profil rekening perusahaan (`BNI`, `BRI`, `BRI Operasional`, `Bank Jago`, `Kas Operasional`), saldo akhir mutasi, arus kas struk internal, dan total 14 kategori SOP secara dinamis dari SQLite. |

---

## Alur Kerja Utama Sistem

```text
  [Input Struk (Staff/Finance/Mgmt)] ──► Vision AI + Rules ──► transaksi_internal
                                                                       │
  [Input Mutasi PDF (Finance/Mgmt)]  ──► Jalur 1: Teks BRI IBBIZ       ├──► Auto-Rekonsiliasi
                                         Jalur 2: Render PNG + Vision  │    (rekonsiliasi_match)
                                                                       ▼
                                                              mutasi_bank & Status Cocok
```

---

## Struktur Proyek

```text
.
├── docs/
│   ├── REQUIREMENT_INPUT_STRUK.md      # Spesifikasi menu Input Struk
│   └── REQUIREMENT_INPUT_MUTASI.md     # Spesifikasi menu Input Mutasi Bank
├── Bukti_Terstruktur_Januari_2026/     # Sampel data struk & PDF mutasi bank
├── backend/
│   ├── .venv/                          # Python Virtual Environment (tidak di-commit)
│   ├── app/
│   │   ├── __main__.py                 # CLI runner (--env-file, --reload, --host, --port)
│   │   ├── main.py                     # Factory FastAPI, registrasi router & static UI
│   │   ├── core/
│   │   │   ├── config.py               # Settings (SECRET_KEY, DATABASE_PATH, VISION_*)
│   │   │   ├── database.py             # Schema SQLite, RBAC & seed master rekening/SOP
│   │   │   ├── password.py             # Hashing & verifikasi password
│   │   │   └── security.py             # Bearer token & dependency require_menu()
│   │   ├── prompts/
│   │   │   ├── receipt_extraction.prompt.md
│   │   │   └── mutasi_extraction.prompt.md
│   │   ├── routers/
│   │   │   ├── auth.py                 # Login & profil user (/auth)
│   │   │   ├── home.py                 # Menu Home (/home)
│   │   │   ├── struk.py                # Menu Input Struk (/struk)
│   │   │   ├── mutasi.py               # Menu Input Mutasi (/mutasi)
│   │   │   └── rekonsiliasi.py         # Menu Rekonsiliasi (/rekonsiliasi)
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── struk.py
│   │   │   ├── mutasi.py
│   │   │   └── bank_statement.py
│   │   └── services/
│   │       ├── auth_service.py         # Autentikasi berbasis SQLite
│   │       ├── vision.py               # Wrapper LiteLLM Vision AI
│   │       ├── storage.py              # Penyimpanan file lampiran aman
│   │       ├── struk_service.py        # Ekstraksi, validasi SOP & simpan struk
│   │       ├── mutasi_parser.py        # Parser 2 jalur (BRI deterministik & Vision per halaman)
│   │       ├── mutasi_service.py       # Preview, cek saldo, dedup & simpan batch mutasi
│   │       ├── rekonsiliasi_service.py # Auto-match struk <-> mutasi & recalculate
│   │       ├── excel_export.py         # Utilitas ekspor Cash Report ke .xlsx
│   │       └── ...                     # Modul utilitas bank statement & mapper
│   ├── tests/                          # Suite automated test (pytest)
│   ├── pyproject.toml
│   ├── requirements.txt                # Dependencies dev + pytest
│   └── requirements-prod.txt           # Dependencies runtime produksi
├── frontend/
│   ├── index.html                      # Shell UI (Tailwind CDN + Plus Jakarta Sans)
│   ├── css/styles.css                  # Animasi & utility styling
│   └── js/
│       ├── api.js                      # Helper HTTP fetch & session token (/api/v1)
│       ├── app.js                      # Login, navigasi desktop/mobile & router menu
│       └── menus/
│           ├── shared.js               # Komponen UI bersama
│           ├── home.js                 # Menu Home
│           ├── inputStruk.js           # Wizard & riwayat Input Struk
│           ├── inputMutasi.js          # Wizard, modal edit & riwayat Input Mutasi
│           └── rekonsiliasi.js         # Menu Rekonsiliasi
├── run.ps1                             # Dev runner Windows (-EnvFile, -Docker, -NoReload)
├── run.sh                              # Dev runner Linux/macOS (--env-file, --docker)
├── Dockerfile                          # Image produksi (FastAPI menyajikan API + UI)
├── docker-compose.yml                  # Compose + persistent volume SQLite (/data)
├── .env.example                        # Template konfigurasi environment
└── README.md
```

---

## Setup & Menjalankan Aplikasi

> **Catatan Konfigurasi:** Runner Windows (`.\run.ps1`) otomatis memakai file `.env` di root project jika tersedia, serta otomatis mengisi data seed Januari 2026 jika database masih kosong. Untuk menjalankan backend langsung (`python -m app`) atau `./run.sh`, berikan `--env-file .env` secara eksplisit.

### 1. Siapkan Virtual Environment & `.env`

Jika `backend/.venv` belum ada:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
cd ..
```

Salin `.env.example` menjadi `.env`, lalu isi `SECRET_KEY`, `VISION_MODEL`, dan `VISION_API_KEY`:

```powershell
Copy-Item .env.example .env
```

```env
SECRET_KEY=isi-dengan-string-acak-panjang
VISION_MODEL=gemini/gemini-3.5-flash-lite
VISION_API_KEY=isi-dengan-api-key-provider-anda
```

*(Opsional: buat nilai `SECRET_KEY` acak dengan `python -c "import secrets; print(secrets.token_urlsafe(48))"`)*.

### 2. Menjalankan Mode Development (Cara Tercepat)

FastAPI menyajikan API sekaligus UI statis (`frontend/`) pada origin yang sama (`http://127.0.0.1:8000`).

- **Windows (PowerShell):**
  ```powershell
  .\run.ps1
  ```
  Jika terblokir ExecutionPolicy:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\run.ps1
  ```
- **Linux / macOS:**
  ```bash
  ./run.sh --env-file .env
  ```

Opsi tambahan pada runner:
- Tanpa auto-reload: `.\run.ps1 -NoReload` atau `./run.sh --no-reload --env-file .env`
- Reset & isi ulang data seed Januari 2026: `.\run.ps1 -Seed` (atau `.\backend\.venv\Scripts\python.exe -m app.seed --reset` dari `backend/`)
- Lewati auto-seed saat database kosong: `.\run.ps1 -NoSeed`
- Tanpa membaca `.env`: `.\run.ps1 -NoEnv` atau `./run.sh`

### 3. Menjalankan Backend Secara Manual

```powershell
cd backend
.\.venv\Scripts\python.exe -m app --reload --env-file ..\.env
```

### 4. Menjalankan dengan Docker

```bash
./run.sh --docker --env-file .env
# atau di Windows:
.\run.ps1 -Docker -EnvFile .env
```

Atau langsung via Docker Compose / Docker CLI:

```bash
APP_ENV_FILE=.env docker compose --env-file .env up --build
```

```bash
docker build -t tugasakhir-g2:latest .
docker run --env-file .env -p 8000:8000 -v app-data:/data tugasakhir-g2:latest
```

Database SQLite pada Docker dipersistenkan di volume `app-data` (`/data/app.db`).

### URL Akses
- **Aplikasi Web (UI):** `http://127.0.0.1:8000`
- **API Base Prefix:** `http://127.0.0.1:8000/api/v1`
- **Swagger UI Docs:** `http://127.0.0.1:8000/docs`
- **Health Check:** `http://127.0.0.1:8000/health`

---

## Akun Demo & Hak Akses (SQLite RBAC)

Database SQLite (`backend/app.db`) otomatis dibuat dan di-seed saat startup dengan data master rekening perusahaan (`BNI`, `BRI`, `BRI Operasional`, `Bank Jago`, `Kas Operasional`), 14 kategori SOP, rekening dikecualikan, serta 3 akun demo:

| Username | Password | Role | Akses Menu |
| :--- | :--- | :--- | :--- |
| `management` | `management123` | `management` | **Home**, **Input Struk**, **Input Mutasi**, **Rekonsiliasi** |
| `finance` | `finance123` | `finance` | **Home**, **Input Struk**, **Input Mutasi**, **Rekonsiliasi** |
| `staff` | `staff123` | `staff` | Hanya **Input Struk** (endpoint menu lain ditolak `403 Forbidden`) |

---

## Endpoint API Utama

| Group | Endpoint | Keterangan |
| :--- | :--- | :--- |
| **Auth** | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | Autentikasi bearer token & cek profil/izin menu. |
| **Input Struk** | `GET /api/v1/struk/metadata`, `POST /api/v1/struk/extract`, `POST /api/v1/struk/save`, `GET /api/v1/struk/recent`, `PUT /api/v1/struk/{id}`, `DELETE /api/v1/struk/{id}`, `GET /api/v1/struk/files/{filename}` | Ekstraksi Vision AI, validasi aturan tab, penyimpanan transaksi & lampiran, serta auto-rekonsiliasi. |
| **Input Mutasi** | `GET /api/v1/mutasi/metadata`, `POST /api/v1/mutasi/preview`, `POST /api/v1/mutasi/save`, `GET /api/v1/mutasi/batches`, `GET /api/v1/mutasi/rows`, `DELETE /api/v1/mutasi/batches/{batch_id}` | Ekstraksi PDF 2 jalur, cek saldo & duplikat, simpan batch + `dedup_signature`, filter riwayat mutasi, dan kalkulasi ulang rekonsiliasi saat hapus batch. |
| **Home & Rekon** | `GET /api/v1/home`, `GET /api/v1/rekonsiliasi` | Data ringkasan Home & placeholder menu Rekonsiliasi. |

---

## Menjalankan Automated Test

Jalankan seluruh suite test (`pytest`) dari folder `backend/`:

```powershell
cd backend
.\.venv\Scripts\pytest.exe -v
```

*(Saat ini mencakup 82 automated tests untuk RBAC, schema SQLite, CLI env loader, Vision client, alur Input Struk, Input Mutasi 2 jalur, dan rekonsiliasi).*

---

## Panduan Menambah Menu / Fitur Baru

1. Buat schema Pydantic di `backend/app/schemas/<fitur>.py`.
2. Buat logika bisnis & query SQLite di `backend/app/services/<fitur>_service.py`.
3. Buat router endpoint di `backend/app/routers/<fitur>.py` (gunakan `Depends(require_menu("<menu_key>"))` untuk proteksi RBAC).
4. Daftarkan router di `backend/app/main.py` via `app.include_router(<fitur>.router, prefix=settings.api_prefix)`.
5. Tambahkan modul UI di `frontend/js/menus/<fitur>.js` dan hubungkan pada mapping menu di `frontend/js/app.js`.
6. Tambahkan unit/integration test di `backend/tests/test_<fitur>.py`.
