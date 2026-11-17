# FastAPI + Separated UI Starter

Template sederhana untuk membangun aplikasi dengan **FastAPI (Backend)** dan **UI terpisah (Frontend)** menggunakan arsitektur modular yang mudah dikembangkan.

## Struktur Proyek

```text
.
├── backend/
│   ├── .venv/                  # Python Virtual Environment (tidak di-commit)
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py       # Konfigurasi app, SQLite path, secret key & CORS (.env)
│   │   │   ├── database.py     # Koneksi SQLite, schema tabel & seed awal
│   │   │   ├── password.py     # Hashing & verifikasi password
│   │   │   └── security.py     # Token & dependency require_menu() berbasis SQLite
│   │   ├── routers/
│   │   │   ├── auth.py         # Endpoint login & profil user (/auth)
│   │   │   ├── home.py         # Endpoint menu Home (/home)
│   │   │   ├── struk.py        # Endpoint menu Input Struk (/struk)
│   │   │   ├── mutasi.py       # Endpoint menu Input Mutasi (/mutasi)
│   │   │   └── rekonsiliasi.py # Endpoint menu Rekonsiliasi (/rekonsiliasi)
│   │   ├── schemas/
│   │   │   └── auth.py         # Schema login, token, UserRole & allowed_menus
│   │   ├── services/
│   │   │   └── auth_service.py # Autentikasi akun demo (management, finance & staff)
│   │   └── main.py             # Entry point FastAPI & registrasi router
│   ├── tests/
│   │   └── test_api.py         # Automated test dengan pytest
│   ├── .env.example            # Contoh file environment variables
│   ├── pyproject.toml          # Konfigurasi pytest (pythonpath)
│   └── requirements.txt        # Daftar library Python backend
├── frontend/
│   ├── index.html              # Shell UI (Tailwind + Plus Jakarta Sans)
│   ├── css/
│   │   └── styles.css          # Styling & animasi ringan
│   └── js/
│       ├── api.js              # Helper fetch ke Backend API & session token
│       ├── app.js              # Entry point: login, navigasi desktop/mobile & router menu
│       └── menus/              # Modul terpisah per menu
│           ├── shared.js       # Helper UI bersama antar menu
│           ├── home.js         # Menu Home
│           ├── inputStruk.js   # Menu Input Struk
│           ├── inputMutasi.js  # Menu Input Mutasi
│           └── rekonsiliasi.js # Menu Rekonsiliasi
├── run.ps1                     # Script PowerShell untuk menjalankan Backend + Frontend sekaligus
├── .gitignore
└── README.md
```

### Kenapa Arsitektur Ini Mudah Di-develop?
1. **UI & Backend Terpisah (`frontend/` vs `backend/`)**:
   - Backend murni menyediakan REST API + Swagger docs (`/docs`).
   - Frontend hanya memanggil endpoint via HTTP (`fetch`), sehingga mudah diganti ke React/Vue/Next.js kapan saja tanpa mengubah backend.
2. **Pemisahan Layer di Backend**:
   - `schemas/` -> Mengatur bentuk data masuk/keluar & validasi otomatis.
   - `services/` -> Berisi logika bisnis / akses database, sehingga kode tetap bersih dan mudah dites.
   - `routers/` -> Hanya menangani HTTP request/response dan memanggil `services/`.
   - `core/` -> Menyimpan konfigurasi terpusat (`CORS`, prefix API, env).

---

## Cara Setup & Menjalankan

### 1. Backend (FastAPI + Virtual Environment)

Virtual environment sudah disiapkan di `backend/.venv`. Jika ingin membuat ulang dari awal atau di mesin lain:

```powershell
cd backend
python -m venv .venv
```

Aktifkan virtual environment:

- **Windows (PowerShell):**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **Windows (CMD):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

Install dependencies (jika belum terinstall):

```powershell
pip install -r requirements.txt
```

(Opsional) Salin `.env.example` menjadi `.env`:

```powershell
Copy-Item .env.example .env
```

Jalankan server FastAPI:

```powershell
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

Backend akan berjalan di:
- API Base URL: `http://127.0.0.1:8000`
- Swagger API Docs: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/health`

---

### 2. Frontend (UI Terpisah)

Buka terminal baru (biarkan backend tetap berjalan), lalu jalankan static server di folder `frontend/`:

```powershell
cd frontend
python -m http.server 3000
```

Buka browser dan akses:
- `http://127.0.0.1:3000`

> Alternatif: Anda juga bisa menggunakan ekstensi **Live Server** di VS Code (`http://127.0.0.1:5500`) karena port `5500` sudah diizinkan di CORS `backend/app/core/config.py`.

---

### 3. Menjalankan Keduanya Sekaligus (PowerShell)

Jika ingin menjalankan backend + frontend sekaligus dalam satu terminal:

```powershell
.\run.ps1
```

Atau jika terblokir ExecutionPolicy:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Tekan `Ctrl+C` untuk menghentikan kedua service.

---

## Menjalankan Test

Jalankan `pytest` di folder `backend/`:

```powershell
cd backend
.\.venv\Scripts\pytest.exe
```

---

## Login, Menu & Role (SQLite RBAC)

Data user, role, dan hak akses menu disimpan di SQLite (`backend/app.db`) yang otomatis dibuat dan di-seed saat server dijalankan pertama kali:
- Tabel `roles` — daftar role (`management`, `finance`, `staff`)
- Tabel `role_menus` — relasi izin menu per role (`home`, `input_struk`, `input_mutasi`, `rekonsiliasi`)
- Tabel `users` — akun user beserta `password_hash` dan `role_id`

| Username | Password | Role | Akses Menu |
| :--- | :--- | :--- | :--- |
| `management` | `management123` | `management` | Semua menu (**Home**, **Input Struk**, **Input Mutasi**, **Rekonsiliasi**) |
| `finance` | `finance123` | `finance` | Semua menu (**Home**, **Input Struk**, **Input Mutasi**, **Rekonsiliasi**) |
| `staff` | `staff123` | `staff` | Hanya **Input Struk** (endpoint menu lain ditolak `403 Forbidden`) |

Endpoint autentikasi:
- `POST /api/v1/auth/login` — Login untuk mendapatkan `access_token` dan info `user`
- `GET /api/v1/auth/me` — Cek profil & role user yang sedang login

---

## Cara Menambah Fitur Baru

Misal ingin menambah fitur `users`:
1. Buat `backend/app/schemas/user.py` (model Pydantic request/response).
2. Buat `backend/app/services/user_service.py` (logika bisnis/database).
3. Buat `backend/app/routers/users.py` (endpoint FastAPI).
4. Daftarkan router di `backend/app/main.py`:
   ```python
   from app.routers import items, users
   app.include_router(users.router, prefix=settings.api_prefix)
   ```
5. Panggil endpoint baru tersebut dari `frontend/app.js`.
