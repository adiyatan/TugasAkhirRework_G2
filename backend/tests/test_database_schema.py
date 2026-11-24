from pathlib import Path
import sqlite3
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Menggunakan database SQLite terpisah untuk setiap test."""
    test_db = tmp_path / "test_schema.db"
    monkeypatch.setattr(settings, "database_path", str(test_db))
    init_db()


def test_all_tables_and_master_seeds_created_idempotently(isolated_sqlite_db: None) -> None:
    # Panggil init_db kedua kali untuk memastikan idempotency
    init_db()

    expected_tables = {
        "roles",
        "role_menus",
        "users",
        "rekening_perusahaan",
        "kategori_sop",
        "rekening_dikecualikan",
        "upload_staging",
        "transaksi_internal",
        "file_bukti_log",
        "mutasi_upload_batch",
        "mutasi_bank",
        "rekonsiliasi_match",
        "ai_config",
        "ai_usage_log",
        "ai_eval_runs",
    }

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        actual_tables = {row["name"] for row in rows}
        assert expected_tables.issubset(actual_tables)

        assert conn.execute("SELECT COUNT(*) FROM rekening_perusahaan").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM kategori_sop").fetchone()[0] == 14
        assert conn.execute("SELECT COUNT(*) FROM rekening_dikecualikan").fetchone()[0] == 1


def test_legacy_single_bank_jago_migrates_to_two_pockets(isolated_sqlite_db: None) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM rekening_perusahaan WHERE kode_akun = 'Bank Jago (Kantong 2)'")
        conn.execute(
            """
            UPDATE rekening_perusahaan
            SET kode_akun = 'Bank Jago',
                no_rekening = '508090335901, 500812786602'
            WHERE kode_akun = 'Bank Jago (Kantong 1)'
            """
        )
        conn.commit()

    init_db()

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT kode_akun, no_rekening FROM rekening_perusahaan ORDER BY id ASC"
        ).fetchall()
        accounts = {row["kode_akun"]: row["no_rekening"] for row in rows}
        assert "Bank Jago" not in accounts
        assert accounts["Bank Jago (Kantong 1)"] == "508090335901"
        assert accounts["Bank Jago (Kantong 2)"] == "500812786602"
        assert len(rows) == 6


def test_struk_mutasi_matching_relations_and_constraints(isolated_sqlite_db: None) -> None:
    with get_connection() as conn:
        staff_id = conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()["id"]
        bni_id = conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"]
        kat_id = conn.execute(
            "SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'"
        ).fetchone()["id"]

        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, expires_at)
            VALUES ('stg_001', ?, 'flip', 0, 'SAVED', '[]', '2026-11-17T17:00:00')
            """,
            (staff_id,),
        )

        cur = conn.execute(
            """
            INSERT INTO transaksi_internal (
                staging_id, created_by_user_id, nama_admin, tanggal_input,
                sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                rekening_sumber_id, tipe, kategori_id, penerima_pengirim,
                keterangan, nominal_pokok, biaya_admin_kode_unik, total_mutasi
            ) VALUES (
                'stg_001', ?, 'Tim Staff', '2026-11-17',
                'INPUT_STRUK', 'flip', '2026-01-01', '16:28:57',
                ?, 'KELUAR', ?, 'Eling Muhammad Falah',
                'Pembelian tepung beras via Flip', 800000, 353, 800353
            )
            """,
            (staff_id, bni_id, kat_id),
        )
        tx_id = cur.lastrowid

        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename,
                file_hash, jenis_struk, status_file, nominal_raw, tanggal_waktu_raw
            ) VALUES (?, 'A', '20261117_01_A.jpg', 'bni_flip.jpg', 'hash_abc', 'BNI_TO_FLIP', 'TERPAKAI_UTAMA', 800353, '2026-01-01 16:28:57')
            """,
            (tx_id,),
        )

        # Hash foto duplikat harus ditolak
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO file_bukti_log (
                    transaksi_internal_id, slot, filename, orig_filename,
                    file_hash, jenis_struk, status_file
                ) VALUES (?, 'B', '20261117_02_B.jpg', 'bni_flip_copy.jpg', 'hash_abc', 'BNI_TO_FLIP', 'TERPAKAI_PENDUKUNG_FLIP')
                """,
                (tx_id,),
            )

        batch_id = conn.execute(
            """
            INSERT INTO mutasi_upload_batch (
                rekening_id, uploaded_by_user_id, nama_file, file_hash, metode_ekstraksi, jumlah_baris
            ) VALUES (?, ?, 'mutasi_bni_jan.pdf', 'pdf_hash_001', 'Gemini Vision', 1)
            """,
            (bni_id, staff_id),
        ).lastrowid

        mut_id = conn.execute(
            """
            INSERT INTO mutasi_bank (
                batch_id, rekening_id, no_rekening, tanggal, waktu,
                uraian, tipe, nominal, saldo, dedup_signature
            ) VALUES (?, ?, '1783680837', '2026-01-01', '16:28:32', 'Transfer PT FLIPTECH', 'DB', 800353, 1380359, 'sig_001')
            """,
            (batch_id, bni_id),
        ).lastrowid

        conn.execute(
            """
            INSERT INTO rekonsiliasi_match (
                match_group_id, transaksi_internal_id, mutasi_bank_id,
                jenis_match, peran_mutasi, selisih_nominal
            ) VALUES ('grp_001', ?, ?, 'EXACT', 'UTAMA', 0)
            """,
            (tx_id, mut_id),
        )

        # Hapus transaksi harus cascade menghapus log file & record match
        conn.execute("DELETE FROM transaksi_internal WHERE id = ?", (tx_id,))
        assert conn.execute("SELECT COUNT(*) FROM file_bukti_log").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM rekonsiliasi_match").fetchone()[0] == 0
