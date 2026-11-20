from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import seed
from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app


@pytest.fixture()
def isolated_home_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "home_test.db"
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "storage_dir", str(storage_dir))
    init_db()
    return tmp_path


def _finance_headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "finance", "password": "finance123"},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_home_reflects_empty_database(isolated_home_db: Path) -> None:
    client = TestClient(app)
    headers = _finance_headers(client)

    res = client.get("/api/v1/home", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["perusahaan"] == "PT Lokal Komoditi Indonesia"
    assert [a["nama_akun"] for a in data["rekening"]] == [
        "BNI",
        "BRI",
        "BRI Operasional",
        "Bank Jago",
        "Kas Operasional",
    ]
    for acc in data["rekening"]:
        assert acc["masuk_fmt"] == "Rp0"
        assert acc["keluar_fmt"] == "Rp0"
        assert acc["pindah_buku_fmt"] == "Rp0"
        assert acc["jumlah_struk"] == 0
        assert acc["jumlah_mutasi"] == 0
        assert acc["has_mutasi"] is False
        expected_saldo = "Kas Tunai" if acc["is_cash"] else "Belum ada mutasi"
        assert acc["saldo_akhir_fmt"] == expected_saldo

    assert len(data["kategori"]) == 14
    for cat in data["kategori"]:
        assert cat["total_nominal"] == 0
        assert cat["total_nominal_fmt"] == "Rp0"
        assert cat["jumlah_transaksi"] == 0

    assert data["ringkasan"] == {
        "total_pemasukan": 0,
        "total_pemasukan_fmt": "Rp0",
        "jumlah_pemasukan": 0,
        "total_pengeluaran": 0,
        "total_pengeluaran_fmt": "Rp0",
        "jumlah_pengeluaran": 0,
        "selisih_bersih": 0,
        "selisih_bersih_fmt": "Rp0",
        "total_pindah_buku": 0,
        "total_pindah_buku_fmt": "Rp0",
        "jumlah_pindah_buku": 0,
    }


def test_home_reflects_live_transactions_and_mutasi(isolated_home_db: Path) -> None:
    with closing(get_connection()) as conn:
        bni_id = conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"]
        bri_ops_id = conn.execute(
            "SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BRI Operasional'"
        ).fetchone()["id"]
        kat_bahan = conn.execute(
            "SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'"
        ).fetchone()["id"]
        kat_pindah = conn.execute(
            "SELECT id FROM kategori_sop WHERE nama_kategori = 'Transfer Antar Rekening (Pindah Buku)'"
        ).fetchone()["id"]

        conn.execute(
            """
            INSERT INTO transaksi_internal (
                nama_admin, tanggal_input, tanggal_transaksi, rekening_sumber_id,
                tipe, kategori_id, nominal_pokok, biaya_admin_kode_unik, total_mutasi
            ) VALUES ('Tester', '2026-02-01', '2026-02-01', ?, 'KELUAR', ?, 50000, 0, 50000)
            """,
            (bni_id, kat_bahan),
        )
        conn.execute(
            """
            INSERT INTO transaksi_internal (
                nama_admin, tanggal_input, tanggal_transaksi, rekening_sumber_id,
                rekening_tujuan_id, tipe, kategori_id, nominal_pokok,
                biaya_admin_kode_unik, total_mutasi
            ) VALUES ('Tester', '2026-02-01', '2026-02-02', ?, ?, 'PINDAH_BUKU', ?, 200000, 350, 200350)
            """,
            (bni_id, bri_ops_id, kat_pindah),
        )
        batch_id = conn.execute(
            """
            INSERT INTO mutasi_upload_batch (
                rekening_id, nama_file, file_hash, periode_mulai, periode_selesai, jumlah_baris
            ) VALUES (?, 'bni.pdf', 'hash1', '2026-02-01', '2026-02-02', 2)
            """,
            (bni_id,),
        ).lastrowid
        # Same timestamp tie: saldo chain 1.000.000 -> +661 -> -5.000 = 995.661
        conn.execute(
            """
            INSERT INTO mutasi_bank (
                batch_id, rekening_id, no_rekening, tanggal, waktu, uraian,
                tipe, nominal, saldo, dedup_signature
            ) VALUES (?, ?, '1783680837', '2026-02-02', '23:59:59', 'Admin', 'DB', 5000, 995661, 'sig2')
            """,
            (batch_id, bni_id),
        )
        conn.execute(
            """
            INSERT INTO mutasi_bank (
                batch_id, rekening_id, no_rekening, tanggal, waktu, uraian,
                tipe, nominal, saldo, dedup_signature
            ) VALUES (?, ?, '1783680837', '2026-02-02', '23:59:59', 'Bunga', 'CR', 661, 1000661, 'sig1')
            """,
            (batch_id, bni_id),
        )
        conn.commit()

    client = TestClient(app)
    res = client.get("/api/v1/home", headers=_finance_headers(client))
    assert res.status_code == 200
    data = res.json()

    accounts = {a["nama_akun"]: a for a in data["rekening"]}
    assert accounts["BNI"]["saldo_akhir_fmt"] == "Rp995.661"
    assert accounts["BNI"]["keluar_fmt"] == "Rp50.000"
    assert accounts["BNI"]["pindah_buku_fmt"] == "Rp200.350"
    assert accounts["BNI"]["jumlah_struk"] == 2
    assert accounts["BNI"]["jumlah_mutasi"] == 2
    assert accounts["BNI"]["has_mutasi"] is True

    assert accounts["BRI Operasional"]["pindah_buku_fmt"] == "Rp200.000"
    assert accounts["BRI Operasional"]["jumlah_struk"] == 1

    categories = {c["nama"]: c for c in data["kategori"]}
    assert categories["Bahan Baku"]["total_nominal"] == 50000
    assert categories["Bahan Baku"]["total_nominal_fmt"] == "Rp50.000"
    assert categories["Bahan Baku"]["jumlah_transaksi"] == 1
    assert categories["Transfer Antar Rekening (Pindah Buku)"]["total_nominal"] == 200350
    assert categories["Transfer Antar Rekening (Pindah Buku)"]["jumlah_transaksi"] == 1


def test_home_with_seeded_januari_2026(isolated_home_db: Path) -> None:
    seed.seed_januari_2026(only_if_empty=True)

    client = TestClient(app)
    res = client.get("/api/v1/home", headers=_finance_headers(client))
    assert res.status_code == 200
    data = res.json()

    accounts = {a["nama_akun"]: a for a in data["rekening"]}
    assert accounts["BNI"]["saldo_akhir_fmt"] == "Rp9.556.974"
    assert accounts["BNI"]["masuk_fmt"] == "Rp6.617.783"
    assert accounts["BNI"]["keluar_fmt"] == "Rp12.207.981"
    assert accounts["BNI"]["pindah_buku_fmt"] == "Rp1.011.607"
    assert accounts["BNI"]["jumlah_struk"] == 62
    assert accounts["BNI"]["jumlah_mutasi"] == 84

    assert accounts["BRI"]["saldo_akhir_fmt"] == "Rp192.643.952"
    assert accounts["BRI"]["jumlah_mutasi"] == 14
    assert accounts["BRI"]["jumlah_struk"] == 0

    assert accounts["BRI Operasional"]["keluar_fmt"] == "Rp350.325"
    assert accounts["BRI Operasional"]["pindah_buku_fmt"] == "Rp800.000"
    assert accounts["BRI Operasional"]["jumlah_struk"] == 5

    assert accounts["Bank Jago"]["keluar_fmt"] == "Rp267.000"
    assert accounts["Bank Jago"]["pindah_buku_fmt"] == "Rp210.000"
    assert accounts["Bank Jago"]["jumlah_struk"] == 5

    assert accounts["Kas Operasional"]["saldo_akhir_fmt"] == "Kas Tunai"
    assert accounts["Kas Operasional"]["keluar_fmt"] == "Rp13.000"
    assert accounts["Kas Operasional"]["jumlah_struk"] == 1

    categories = {c["nama"]: c for c in data["kategori"]}
    assert categories["Bahan Baku"]["total_nominal"] == 2480220
    assert categories["Bahan Baku"]["jumlah_transaksi"] == 6
    assert categories["Biaya-Gaji Karyawan"]["total_nominal"] == 5463654
    assert categories["Biaya-Gaji Karyawan"]["jumlah_transaksi"] == 6
    assert categories["Transfer Antar Rekening (Pindah Buku)"]["total_nominal"] == 1011607
    assert categories["Transfer Antar Rekening (Pindah Buku)"]["jumlah_transaksi"] == 5

    assert data["ringkasan"] == {
        "total_pemasukan": 6617783,
        "total_pemasukan_fmt": "Rp6.617.783",
        "jumlah_pemasukan": 12,
        "total_pengeluaran": 12838306,
        "total_pengeluaran_fmt": "Rp12.838.306",
        "jumlah_pengeluaran": 51,
        "selisih_bersih": -6220523,
        "selisih_bersih_fmt": "-Rp6.220.523",
        "total_pindah_buku": 1011607,
        "total_pindah_buku_fmt": "Rp1.011.607",
        "jumlah_pindah_buku": 5,
    }


def test_home_month_filter(isolated_home_db: Path) -> None:
    seed.seed_januari_2026(only_if_empty=True)

    with closing(get_connection()) as conn:
        bni_id = conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"]
        kat_bahan = conn.execute(
            "SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO transaksi_internal (
                nama_admin, tanggal_input, tanggal_transaksi, rekening_sumber_id,
                tipe, kategori_id, nominal_pokok, biaya_admin_kode_unik, total_mutasi
            ) VALUES ('Tester', '2026-02-05', '2026-02-05', ?, 'KELUAR', ?, 100000, 0, 100000)
            """,
            (bni_id, kat_bahan),
        )
        conn.commit()

    client = TestClient(app)
    headers = _finance_headers(client)

    all_res = client.get("/api/v1/home", headers=headers)
    assert all_res.status_code == 200
    all_data = all_res.json()
    assert all_data["bulan"] is None
    assert all_data["periode_label"] == "Semua Periode"
    assert all_data["ringkasan"]["total_pengeluaran"] == 12838306 + 100000

    jan_res = client.get("/api/v1/home", params={"bulan": "2026-01"}, headers=headers)
    assert jan_res.status_code == 200
    jan_data = jan_res.json()
    assert jan_data["bulan"] == "2026-01"
    assert jan_data["periode_label"] == "Januari 2026"
    assert jan_data["ringkasan"]["total_pemasukan"] == 6617783
    assert jan_data["ringkasan"]["total_pengeluaran"] == 12838306
    jan_accounts = {a["nama_akun"]: a for a in jan_data["rekening"]}
    assert jan_accounts["BNI"]["saldo_akhir_fmt"] == "Rp9.556.974"
    assert jan_accounts["BNI"]["jumlah_mutasi"] == 84

    feb_res = client.get("/api/v1/home", params={"bulan": "2026-02"}, headers=headers)
    assert feb_res.status_code == 200
    feb_data = feb_res.json()
    assert feb_data["bulan"] == "2026-02"
    assert feb_data["periode_label"] == "Februari 2026"
    assert feb_data["ringkasan"]["total_pemasukan"] == 0
    assert feb_data["ringkasan"]["total_pengeluaran"] == 100000
    assert feb_data["ringkasan"]["jumlah_pengeluaran"] == 1
    feb_accounts = {a["nama_akun"]: a for a in feb_data["rekening"]}
    assert feb_accounts["BNI"]["keluar_fmt"] == "Rp100.000"
    assert feb_accounts["BNI"]["jumlah_mutasi"] == 0
    assert feb_accounts["BNI"]["has_mutasi"] is False
    assert feb_accounts["BNI"]["saldo_akhir_fmt"] == "Rp9.556.974"

    assert client.get("/api/v1/home", params={"bulan": "2026-13"}, headers=headers).status_code == 422
    assert client.get("/api/v1/home", params={"bulan": "januari"}, headers=headers).status_code == 422
