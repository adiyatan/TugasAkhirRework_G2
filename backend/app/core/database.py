from pathlib import Path
import sqlite3

from app.core.config import settings
from app.core.password import hash_password

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ROLE_MENUS: dict[str, list[str]] = {
    "management": ["home", "input_struk", "input_mutasi", "rekonsiliasi"],
    "finance": ["home", "input_struk", "input_mutasi", "rekonsiliasi"],
    "staff": ["input_struk"],
}

DEFAULT_USERS: list[tuple[str, str, str, str]] = [
    ("management", "Tim Management", "management123", "management"),
    ("finance", "Tim Finance", "finance123", "finance"),
    ("staff", "Tim Staff", "staff123", "staff"),
]

DEFAULT_REKENING_PERUSAHAAN: list[tuple[str, str, str, str, str, int]] = [
    (
        "BNI",
        "Bank BNI (Taplus Muda)",
        "1783680837",
        "ILHAM NAWAN RASYID",
        "Rekening operasional utama (transfer keluar via Flip, QRIS, VA Shopee/PLN/BPJS, penerimaan penjualan)",
        0,
    ),
    (
        "BRI",
        "Bank BRI (BritAma Bisnis)",
        "306601000009566",
        "LOKAL KOMODITI INDONESIA",
        "Rekening bisnis perusahaan (pajak MPN, BRIVA, transfer vendor, & pengisian dana ke BNI via Flip)",
        0,
    ),
    (
        "BRI Operasional",
        "Bank BRI (BRImo)",
        "174601000418533",
        "ILHAM NAWAN RASYID",
        "Kantong uang operasional harian (diisi dari BNI via Flip, belanja alat/aset via BRImo)",
        0,
    ),
    (
        "Bank Jago",
        "Bank Jago / Jago Syariah",
        "508090335901, 500812786602",
        "ILHAM NAWAN RASYID",
        "Kantong operasional ongkir affiliate, reimburse Meta Ads, dan kantong profit share/saving",
        0,
    ),
    (
        "Kas Operasional",
        "Kas Tunai (Cash On Hand)",
        "-",
        "Kas Operasional Perusahaan",
        "Pembayaran tunai langsung di lapangan / resi & nota fisik",
        1,
    ),
]

DEFAULT_KATEGORI_SOP: list[tuple[int, str, str]] = [
    (1, "Bahan Baku", "PENGELUARAN"),
    (2, "Biaya-Gaji Karyawan", "PENGELUARAN"),
    (3, "Biaya-Konsumsi", "PENGELUARAN"),
    (4, "Biaya-Perlengkapan Kantor dan Administrasi", "PENGELUARAN"),
    (5, "Biaya-Transportasi", "PENGELUARAN"),
    (6, "Biaya-Ongkir", "PENGELUARAN"),
    (7, "Biaya-Perbaikan Bangunan", "PENGELUARAN"),
    (8, "Biaya-Operasional", "PENGELUARAN"),
    (9, "Biaya-Pembelian Aset", "PENGELUARAN"),
    (10, "Biaya-Sosial", "PENGELUARAN"),
    (11, "Pendapatan Usaha (Penjualan Lainnya)", "PEMASUKAN"),
    (12, "Pendapatan Usaha (Workshop)", "PEMASUKAN"),
    (13, "Pendapatan/Beban Lain", "PEMASUKAN"),
    (14, "Transfer Antar Rekening (Pindah Buku)", "NON_USAHA"),
]

DEFAULT_REKENING_DIKECUALIKAN: list[tuple[str, str, str]] = [
    ("Muhamad Ali Shodiqi", "0568158096", "Rekening pribadi karyawan (sering muncul pada nota talangan reimburse)"),
]


def get_db_path() -> Path:
    """Mengembalikan path absolut file SQLite."""
    db_path = Path(settings.database_path)
    if not db_path.is_absolute():
        return BACKEND_ROOT / db_path
    return db_path


def get_connection() -> sqlite3.Connection:
    """Membuka koneksi SQLite dengan Row factory dan foreign keys aktif."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _seed_rbac_data(conn: sqlite3.Connection) -> None:
    """Mengisi data awal roles, role_menus, dan users jika belum ada."""
    for role_name, menus in DEFAULT_ROLE_MENUS.items():
        conn.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role_name,))
        role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
        role_id = role_row["id"]
        for menu_key in menus:
            conn.execute(
                "INSERT OR IGNORE INTO role_menus (role_id, menu_key) VALUES (?, ?)",
                (role_id, menu_key),
            )

    for username, full_name, raw_password, role_name in DEFAULT_USERS:
        role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
        if role_row:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (username, full_name, password_hash, role_id)
                VALUES (?, ?, ?, ?)
                """,
                (username, full_name, hash_password(raw_password), role_row["id"]),
            )


def _seed_master_data(conn: sqlite3.Connection) -> None:
    """Mengisi data master rekening perusahaan, kategori SOP, dan rekening dikecualikan."""
    for kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash in DEFAULT_REKENING_PERUSAHAAN:
        conn.execute(
            """
            INSERT OR IGNORE INTO rekening_perusahaan (
                kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash),
        )

    for no_urut, nama_kategori, kelompok in DEFAULT_KATEGORI_SOP:
        conn.execute(
            """
            INSERT OR IGNORE INTO kategori_sop (no_urut, nama_kategori, kelompok)
            VALUES (?, ?, ?)
            """,
            (no_urut, nama_kategori, kelompok),
        )

    for nama_pemilik, potongan_no_rek, keterangan in DEFAULT_REKENING_DIKECUALIKAN:
        conn.execute(
            """
            INSERT OR IGNORE INTO rekening_dikecualikan (nama_pemilik, potongan_no_rek, keterangan)
            VALUES (?, ?, ?)
            """,
            (nama_pemilik, potongan_no_rek, keterangan),
        )


def init_db() -> None:
    """Membuat seluruh tabel SQLite (RBAC, master, struk, mutasi, rekonsiliasi) dan seed awal."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS role_menus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                menu_key TEXT NOT NULL,
                UNIQUE(role_id, menu_key)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL REFERENCES roles(id)
            );

            CREATE TABLE IF NOT EXISTS rekening_perusahaan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode_akun TEXT UNIQUE NOT NULL,
                bank_lembaga TEXT NOT NULL,
                no_rekening TEXT NOT NULL,
                atas_nama TEXT NOT NULL,
                peran TEXT NOT NULL DEFAULT '',
                is_cash INTEGER NOT NULL DEFAULT 0 CHECK(is_cash IN (0, 1)),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS kategori_sop (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                no_urut INTEGER NOT NULL,
                nama_kategori TEXT UNIQUE NOT NULL,
                kelompok TEXT NOT NULL CHECK(kelompok IN ('PENGELUARAN', 'PEMASUKAN', 'NON_USAHA')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS rekening_dikecualikan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama_pemilik TEXT NOT NULL,
                potongan_no_rek TEXT UNIQUE NOT NULL,
                keterangan TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS upload_staging (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                tab_type TEXT NOT NULL CHECK(tab_type IN ('normal', 'flip', 'slip_gaji', 'reimburse')),
                is_cash INTEGER NOT NULL DEFAULT 0 CHECK(is_cash IN (0, 1)),
                status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'SAVED', 'EXPIRED')),
                manifest_json TEXT NOT NULL DEFAULT '[]',
                extracted_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transaksi_internal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staging_id TEXT UNIQUE REFERENCES upload_staging(id) ON DELETE SET NULL,
                created_by_user_id INTEGER REFERENCES users(id),
                nama_admin TEXT NOT NULL,
                tanggal_input TEXT NOT NULL,
                sumber_pencatatan TEXT NOT NULL DEFAULT 'INPUT_STRUK' CHECK(sumber_pencatatan IN ('INPUT_STRUK', 'PENYESUAIAN_MUTASI')),
                tab_type TEXT NOT NULL DEFAULT 'normal' CHECK(tab_type IN ('normal', 'flip', 'slip_gaji', 'reimburse', 'manual')),
                tanggal_transaksi TEXT NOT NULL,
                waktu_transaksi TEXT NOT NULL DEFAULT '12:00:00',
                rekening_sumber_id INTEGER NOT NULL REFERENCES rekening_perusahaan(id),
                rekening_tujuan_id INTEGER REFERENCES rekening_perusahaan(id),
                tipe TEXT NOT NULL CHECK(tipe IN ('MASUK', 'KELUAR', 'PINDAH_BUKU')),
                kategori_id INTEGER NOT NULL REFERENCES kategori_sop(id),
                penerima_pengirim TEXT NOT NULL DEFAULT '',
                keterangan TEXT NOT NULL DEFAULT '',
                nominal_pokok REAL NOT NULL DEFAULT 0 CHECK(nominal_pokok >= 0),
                biaya_admin_kode_unik REAL NOT NULL DEFAULT 0 CHECK(biaya_admin_kode_unik >= 0),
                total_mutasi REAL NOT NULL DEFAULT 0 CHECK(total_mutasi > 0),
                status_rekonsiliasi TEXT NOT NULL DEFAULT 'BELUM_REKON' CHECK(status_rekonsiliasi IN ('BELUM_REKON', 'MUTASI_BELUM_ADA', 'SESUAI', 'SELISIH_KODE_UNIK_ADMIN', 'PINDAH_BUKU_COCOK')),
                catatan_rekonsiliasi TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS file_bukti_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaksi_internal_id INTEGER NOT NULL REFERENCES transaksi_internal(id) ON DELETE CASCADE,
                slot TEXT NOT NULL CHECK(slot IN ('A', 'B', 'C')),
                filename TEXT UNIQUE NOT NULL,
                orig_filename TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                jenis_struk TEXT NOT NULL DEFAULT '',
                status_file TEXT NOT NULL CHECK(status_file IN ('TERPAKAI_UTAMA', 'TERPAKAI_PENDUKUNG_FLIP', 'TERPAKAI_NOTA_PENDUKUNG')),
                nominal_raw REAL NOT NULL DEFAULT 0,
                tanggal_waktu_raw TEXT NOT NULL DEFAULT '',
                keterangan_raw TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS mutasi_upload_batch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rekening_id INTEGER NOT NULL REFERENCES rekening_perusahaan(id),
                uploaded_by_user_id INTEGER REFERENCES users(id),
                nama_file TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                metode_ekstraksi TEXT NOT NULL DEFAULT '',
                periode_mulai TEXT NOT NULL DEFAULT '',
                periode_selesai TEXT NOT NULL DEFAULT '',
                saldo_awal_periode REAL,
                saldo_akhir_periode REAL,
                jumlah_baris INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS mutasi_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL REFERENCES mutasi_upload_batch(id) ON DELETE CASCADE,
                rekening_id INTEGER NOT NULL REFERENCES rekening_perusahaan(id),
                no_rekening TEXT NOT NULL,
                tanggal TEXT NOT NULL,
                waktu TEXT NOT NULL DEFAULT '',
                uraian TEXT NOT NULL,
                tipe TEXT NOT NULL CHECK(tipe IN ('CR', 'DB')),
                nominal REAL NOT NULL CHECK(nominal > 0),
                saldo REAL,
                dedup_signature TEXT UNIQUE NOT NULL,
                status_rekonsiliasi TEXT NOT NULL DEFAULT 'BELUM_REKON' CHECK(status_rekonsiliasi IN ('BELUM_REKON', 'SESUAI', 'SELISIH_KODE_UNIK_ADMIN', 'PINDAH_BUKU', 'BELUM_TERCATAT')),
                penyebab_selisih TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rekonsiliasi_match (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_group_id TEXT NOT NULL,
                transaksi_internal_id INTEGER REFERENCES transaksi_internal(id) ON DELETE CASCADE,
                mutasi_bank_id INTEGER NOT NULL REFERENCES mutasi_bank(id) ON DELETE CASCADE,
                jenis_match TEXT NOT NULL CHECK(jenis_match IN ('EXACT', 'SPLIT_ADMIN', 'TOLERANCE', 'PINDAH_BUKU_PAIR', 'MANUAL')),
                peran_mutasi TEXT NOT NULL DEFAULT 'UTAMA' CHECK(peran_mutasi IN ('UTAMA', 'POKOK', 'BIAYA_ADMIN', 'PINDAH_KELUAR', 'PINDAH_MASUK')),
                selisih_nominal REAL NOT NULL DEFAULT 0,
                is_manual INTEGER NOT NULL DEFAULT 0 CHECK(is_manual IN (0, 1)),
                matched_by_user_id INTEGER REFERENCES users(id),
                catatan TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(transaksi_internal_id, mutasi_bank_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tx_internal_match
                ON transaksi_internal(tanggal_transaksi, rekening_sumber_id, tipe);
            CREATE INDEX IF NOT EXISTS idx_mutasi_bank_match
                ON mutasi_bank(rekening_id, tanggal, tipe);
            CREATE INDEX IF NOT EXISTS idx_rekonsiliasi_group
                ON rekonsiliasi_match(match_group_id);
            CREATE INDEX IF NOT EXISTS idx_rekonsiliasi_mutasi
                ON rekonsiliasi_match(mutasi_bank_id);
            """
        )

        _seed_rbac_data(conn)
        _seed_master_data(conn)
        conn.commit()
