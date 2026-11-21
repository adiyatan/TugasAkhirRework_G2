# Dompet & Akun SOP — PT Lokal Komoditi Indonesia

Aplikasi web untuk mencatat transaksi keuangan dari foto bukti/struk, mengekstrak rekening koran PDF, serta melakukan rekonsiliasi kas/bank dan ekspor **Cash Report** bulanan sesuai 14 kategori SOP perusahaan. Aplikasi ditujukan bagi tim **Management**, **Finance**, dan **Staff**, dengan pembatasan akses di mana peran **Staff** hanya dapat mengakses menu **Input Struk** sedangkan **Management** dan **Finance** dapat mengakses seluruh menu.

---

## Cara menggunakan

1. **Masuk ke aplikasi**
   Buka `http://127.0.0.1:8000` di browser, lalu masuk sebagai **Management**, **Finance**, atau **Staff** menggunakan tombol akun demo pada halaman login. *(Tersedia juga tombol **Reset + Seeding** untuk memuat contoh data Januari 2026 atau **Reset Kosong** untuk mengosongkan transaksi).*

2. **Input Struk *(Staff, Finance, Management)***
   Buka menu **Input Struk**, pilih tab transaksi, unggah foto bukti pada slot yang sesuai, klik **Ekstrak dengan AI**, periksa form review, lalu klik **Simpan Transaksi**:
   - **Normal** *(opsional centang **Tunai / Kas**)*: unggah 1+ foto bukti bayar di **Slot A** *(contoh: foto struk QRIS atau bukti transfer bank)*.
   - **Transfer Flip**: unggah tepat 1 bukti transfer Bank ke Flip di **Slot A** dan 1+ bukti Flip ke penerima di **Slot B** *(opsional nota di **Slot C**)*.
   - **Slip Gaji**: unggah 1+ foto slip gaji di **Slot A** dan 1+ bukti transfer gaji di **Slot B**.
   - **Reimburse**: unggah 1+ foto nota talangan pribadi di **Slot A** dan 1+ bukti transfer penggantian PT di **Slot B**.

3. **Input Mutasi Bank *(Finance, Management)***
   Buka menu **Input Mutasi**, pilih target rekening (atau biarkan **Deteksi Otomatis**), unggah PDF rekening koran *(contoh: `BNI_Mutasi_Januari_2026.pdf` atau `Mutasi Rekening BRI-Januari 2026.pdf`)*, lalu klik **Preview & Ekstrak**. Periksa keseimbangan saldo awal/akhir—perbaiki baris bila ada selisih—kemudian klik **Simpan Batch** untuk menyimpan mutasi dan memicu auto-rekonsiliasi.

4. **Rekonsiliasi & Cash Report *(Finance, Management)***
   Buka menu **Rekonsiliasi**, pilih rekening dan bulan *(contoh: `BNI` · `2026-01`)*, lalu tinjau kecocokan pada tab **Mutasi Bank** dan **Catatan Struk**. Gunakan **Match Manual**, **Penyesuaian Mutasi** *(misalnya biaya admin bank tanpa struk)*, atau **Auto-Rekon Ulang**, lalu buka tampilan **Cash Report** untuk mengunduh laporan Excel (`.xlsx`).

5. **Home *(Finance, Management)***
   Buka menu **Home** untuk memantau saldo rekening perusahaan, arus kas dari Input Struk, serta total transaksi per 14 kategori SOP berdasarkan filter bulan.

---

## Fitur AI

- **Yang dikerjakan AI:**
  - **Input Struk:** Membaca foto bukti (JPEG/PNG/WEBP/HEIC/HEIF) per slot untuk menyusun draf tanggal, waktu, rekening sumber/tujuan, tipe transaksi, kategori SOP, nominal, biaya admin/kode unik, serta mendeteksi struk belum bayar atau rekening dikecualikan.
  - **Input Mutasi (jalur cadangan):** Merender tiap halaman PDF non-teks atau hasil pindaian (seperti BNI Wondr, Bank Jago, dan BRI Operasional) menjadi gambar PNG skala `2.0x`, lalu mengekstrak baris transaksi.
- **Yang tetap berjalan tanpa AI:** Login dan kontrol akses (RBAC), menu **Home**, riwayat/edit/hapus transaksi tersimpan, ekstraksi PDF teks **BRI IBBIZ** lewat parser deterministik (**0 panggilan AI**), validasi saldo dan simpan batch mutasi, seluruh proses **Rekonsiliasi** (auto-match, match manual, penyesuaian mutasi, unmatch), serta ekspor **Cash Report** `.xlsx`.
- **Bila AI gagal:** Jika API key belum diisi, kuota habis, timeout, atau respons AI bukan JSON valid, proses ekstraksi struk maupun preview PDF jalur Vision AI dihentikan dengan pesan error di UI (`502`) dan tidak menyimpan data rusak.

> **Penting:** Keluaran AI **bukan data sumber kebenaran**. Hasil ekstraksi hanyalah draf awal yang tetap divalidasi oleh aturan SOP, pengecekan keseimbangan saldo, dan wajib ditinjau pengguna sebelum disimpan.

---

## Mengatur AI

Simpan konfigurasi di file `.env` pada root repository (salin dari `.env.example` dan jangan di-commit) atau melalui environment variable sistem/container. Aplikasi hanya membaca `.env` bila dijalankan dengan flag `--env-file` (otomatis diteruskan saat memakai `.\run.ps1`).

| Variabel | Fungsi | Contoh Format |
| :--- | :--- | :--- |
| `VISION_MODEL` | Nama model Vision pada format LiteLLM | `<provider>/<model>` |
| `VISION_API_KEY` | API key provider AI yang digunakan | *(isi dengan key lokal Anda)* |
| `SECRET_KEY` | String acak rahasia penandatangan token sesi login | *(isi string acak panjang)* |

> Jangan pernah melakukan commit API key, token, password, atau secret lain ke dalam repository.

---

## Pengaturan batas pemakaian

| Pengaman | Mekanisme yang Diterapkan |
| :--- | :--- |
| **Jalur 0-AI (BRI IBBIZ)** | PDF berbasis teks dari BRI IBBIZ diproses secara deterministik di server lokal tanpa memanggil AI. |
| **Timeout, retry, & token** | Panggilan Vision AI dibatasi `timeout` 120 detik, maksimal 2 kali retry (`num_retries=2`), serta batas `max_tokens` (`4096` struk / `8192` per halaman mutasi). |
| **Anti-duplikat & batas file** | Hash SHA-256 gambar diperiksa sebelum memanggil AI untuk menolak file duplikat; ukuran file dibatasi `MAX_UPLOAD_MB` (default `10` MB). |
| **Staging sementara** | Hasil ekstraksi struk disimpan sementara di `upload_staging` selama `STAGING_TTL_MINUTES` (default `120` menit) agar proses simpan tidak memicu ekstraksi ulang. |
| **Batas kuota provider** | Belum terdapat rate limiter per pengguna/per menit maupun saklar mati AI di UI; pembatasan kuota mengikuti akun provider `VISION_API_KEY`. |

---

## Menjalankan di komputer sendiri

**Prasyarat:** Python 3.11+ dan `pip` (opsional: Docker Desktop).

1. **Buat virtual environment & pasang dependency**
   - Windows (PowerShell):
     ```powershell
     cd backend
     python -m venv .venv
     .\.venv\Scripts\pip.exe install -r requirements.txt
     cd ..
     ```
   - Linux / macOS:
     ```bash
     cd backend
     python3 -m venv .venv
     ./.venv/bin/pip install -r requirements.txt
     cd ..
     ```

2. **Siapkan file `.env`**
   Salin `.env.example` menjadi `.env` di root project, lalu isi `SECRET_KEY`, `VISION_MODEL`, dan `VISION_API_KEY`.

3. **Jalankan aplikasi (`http://127.0.0.1:8000`)**
   - Windows *(otomatis membaca `.env` dan mengisi seed Januari 2026 bila database kosong)*:
     ```powershell
     .\run.ps1
     ```
   - Linux / macOS:
     ```bash
     ./run.sh --env-file .env
     ```
   - Manual dari folder `backend/`:
     ```powershell
     cd backend
     .\.venv\Scripts\python.exe -m app --reload --env-file ..\.env
     ```

4. **Jalankan pengujian (opsional)**
   ```powershell
   cd backend
   .\.venv\Scripts\pytest.exe -v
   ```

---

## Men-deploy

- **Platform / Runtime:** Container **Docker** (`python:3.13-slim`, non-root user `app`) dan **Docker Compose** di port `8000` (menyajikan API dan UI dari satu origin).
- **Berkas utama:** `Dockerfile`, `docker-compose.yml`, `backend/requirements-prod.txt`, `backend/app/__main__.py`, dan `backend/app/main.py`.
- **Perintah build & start:**
  ```bash
  APP_ENV_FILE=.env docker compose --env-file .env up --build
  ```
  *(Atau gunakan `.\run.ps1 -Docker` di Windows dan `./run.sh --docker --env-file .env` di Linux/macOS).*
- **Secrets wajib:** `SECRET_KEY` (wajib diubah dari nilai default karena container memakai `DEBUG=false`), `VISION_MODEL`, dan `VISION_API_KEY`.
- **Catatan runtime:** Data SQLite dipersistenkan pada volume `app-data` (`/data/app.db`) dan status container dipantau oleh healthcheck `/health` setiap 30 detik.

---

## Struktur project

```text
.
├── backend/
│   ├── app/
│   │   ├── __main__.py                 # CLI runner (--env-file, --reload, --host, --port)
│   │   ├── main.py                     # Factory FastAPI, router API & penyaji UI statis
│   │   ├── seed.py                     # Seeder data simulasi Januari 2026
│   │   ├── core/                       # Konfigurasi env, skema SQLite, RBAC & keamanan
│   │   ├── prompts/                    # Template prompt Vision AI (struk & mutasi PDF)
│   │   ├── routers/                    # Endpoint auth, home, struk, mutasi & rekonsiliasi
│   │   ├── schemas/                    # Skema validasi request/response Pydantic
│   │   └── services/                   # Logika bisnis, Vision AI, parser & ekspor Excel
│   ├── tests/                          # Suite pengujian otomatis (pytest)
│   ├── requirements.txt                # Dependency development & pytest
│   └── requirements-prod.txt           # Dependency runtime produksi (Docker)
├── frontend/
│   ├── index.html                      # Shell UI (Tailwind CSS) & halaman login
│   ├── css/styles.css                  # Styling & animasi antarmuka
│   └── js/
│       ├── api.js                      # Helper HTTP fetch & token sesi (/api/v1)
│       ├── app.js                      # Autentikasi, navigasi per role & router menu
│       └── menus/                      # Modul UI Home, Input Struk, Input Mutasi & Rekonsiliasi
├── Bukti_Terstruktur_Januari_2026/     # Data contoh struk & PDF rekening koran
├── run.ps1                             # Runner lokal & Docker untuk Windows
├── run.sh                              # Runner lokal & Docker untuk Linux/macOS
├── Dockerfile                          # Image produksi (FastAPI API + UI statis)
├── docker-compose.yml                  # Orkestrasi container + volume persisten SQLite
├── .env.example                        # Contoh variabel konfigurasi tanpa nilai rahasia
└── README.md                           # Dokumentasi utama repository
```

| Lokasi | Fungsi |
| :--- | :--- |
| `backend/app/main.py` | Factory FastAPI, registrasi router `/api/v1`, healthcheck `/health`, dan penyaji UI statis. |
| `backend/app/core/config.py` | Pembaca konfigurasi environment serta flag eksplisit `--env-file`. |
| `backend/app/core/database.py` | Skema tabel SQLite, inisialisasi role/RBAC, serta master rekening dan 14 kategori SOP. |
| `backend/app/seed.py` | Pengisi data simulasi transaksi, mutasi, dan lampiran Januari 2026 (`--if-empty` / `--reset`). |
| `backend/app/routers/` | Endpoint HTTP untuk `auth`, `home`, `struk`, `mutasi`, dan `rekonsiliasi`. |
| `backend/app/services/` | Ekstraksi struk, parser mutasi 2 jalur, klien Vision AI, penyimpanan file, rekonsiliasi, dan generator `.xlsx`. |
| `backend/app/prompts/` | Prompt Vision AI untuk ekstraksi bukti transaksi dan halaman PDF mutasi. |
| `backend/tests/` | Pengujian otomatis berbasis `pytest` untuk API, database, parser, Vision AI, dan rekonsiliasi. |
| `frontend/index.html` & `js/` | Antarmuka web single-origin tanpa build step untuk seluruh menu sesuai hak akses role. |
| `Bukti_Terstruktur_Januari_2026/` | Kumpulan bukti struk dan PDF rekening koran simulasi untuk pengujian dan seeding. |
| `run.ps1` & `run.sh` | Skrip pintasan untuk menjalankan server pengembangan lokal maupun container Docker. |
| `Dockerfile` & `docker-compose.yml` | Definisi container produksi dengan volume persisten `/data/app.db`. |
| `.env.example` | Daftar variabel environment yang perlu disalin menjadi `.env` secara lokal. |

---

## Keterbatasan

- **Ketergantungan AI pada input:** Ekstraksi **Input Struk** dan PDF rekening koran non-teks memerlukan koneksi internet serta `VISION_API_KEY` aktif; belum tersedia form pengisian Input Struk manual dari nol tanpa melewati tahap ekstraksi AI.
- **Parser 0-AI terbatas:** Ekstraksi deterministik tanpa AI hanya mendukung format teks PDF **BRI IBBIZ**; bank lain atau PDF hasil scan masih bergantung pada Vision AI per halaman.
- **Penyimpanan lokal:** Database menggunakan **SQLite** (`app.db`) dan lampiran disimpan di disk lokal (`backend/storage/`), sehingga belum dirancang untuk deployment multi-instance secara bersamaan.
- **Pemrosesan sinkron & kuota:** Belum tersedia rate limiter per pengguna maupun antrean background job; PDF mutasi diproses halaman demi halaman dalam satu request.
- **Batas unggahan:** Ukuran file dibatasi maksimal `MAX_UPLOAD_MB` (default `10` MB per file) dan lampiran struk hanya menerima format JPEG, PNG, WEBP, atau HEIC/HEIF.
- **Manajemen user tetap:** Hanya tersedia 3 role bawaan (`management`, `finance`, `staff`) tanpa halaman UI untuk menambah akun atau mengubah password.

---

## Catatan data

Seluruh berkas pada folder `Bukti_Terstruktur_Januari_2026/` serta fitur **Reset + Seeding** hanya berisi **data simulasi/contoh** untuk kebutuhan pengujian dan demonstrasi aplikasi. Dilarang mengunggah data keuangan produksi yang bersifat rahasia, kredensial perbankan, atau informasi sensitif nyata ke repository publik maupun layanan AI eksternal tanpa otorisasi dan pengamanan yang sesuai.
