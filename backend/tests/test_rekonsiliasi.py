from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_rekon_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "rekon.db"))
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str = "finance", password: str = "finance123") -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _master_ids() -> dict[str, int]:
    with get_connection() as conn:
        accs = {
            row["kode_akun"]: int(row["id"])
            for row in conn.execute("SELECT id, kode_akun FROM rekening_perusahaan").fetchall()
        }
        cats = {
            row["nama_kategori"]: int(row["id"])
            for row in conn.execute("SELECT id, nama_kategori FROM kategori_sop").fetchall()
        }
        users = {
            row["username"]: int(row["id"])
            for row in conn.execute("SELECT id, username FROM users").fetchall()
        }
    return {"accs": accs, "cats": cats, "users": users}


def _insert_tx(
    *,
    user_id: int,
    nama_admin: str,
    tanggal_transaksi: str,
    waktu_transaksi: str = "12:00:00",
    rekening_sumber_id: int,
    rekening_tujuan_id: int | None = None,
    tipe: str,
    kategori_id: int,
    penerima_pengirim: str = "Pihak A",
    keterangan: str = "Ket",
    nominal_pokok: float,
    biaya_admin: float = 0.0,
    total_mutasi: float,
    status: str = "BELUM_REKON",
) -> int:
    with get_connection() as conn:
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                staging_id, created_by_user_id, nama_admin, tanggal_input,
                sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                rekening_sumber_id, rekening_tujuan_id, tipe, kategori_id,
                penerima_pengirim, keterangan, nominal_pokok,
                biaya_admin_kode_unik, total_mutasi, status_rekonsiliasi
            ) VALUES (NULL, ?, ?, '2026-01-31', 'INPUT_STRUK', 'normal', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                nama_admin,
                tanggal_transaksi,
                waktu_transaksi,
                rekening_sumber_id,
                rekening_tujuan_id,
                tipe,
                kategori_id,
                penerima_pengirim,
                keterangan,
                nominal_pokok,
                biaya_admin,
                total_mutasi,
                status,
            ),
        ).lastrowid
        conn.commit()
    return int(tx_id)


def _insert_mutasi_batch(
    *,
    rekening_id: int,
    user_id: int,
    nama_file: str,
    file_hash: str,
    periode_mulai: str,
    periode_selesai: str,
    saldo_awal: float | None,
    saldo_akhir: float | None,
    rows: list[tuple[str, str, str, str, float, float | None, str]],
) -> list[int]:
    mut_ids: list[int] = []
    with get_connection() as conn:
        batch_id = conn.execute(
            """
            INSERT INTO mutasi_upload_batch (
                rekening_id, uploaded_by_user_id, nama_file, file_hash, metode_ekstraksi,
                periode_mulai, periode_selesai, saldo_awal_periode, saldo_akhir_periode, jumlah_baris
            ) VALUES (?, ?, ?, ?, 'test', ?, ?, ?, ?, ?)
            """,
            (
                rekening_id,
                user_id,
                nama_file,
                file_hash,
                periode_mulai,
                periode_selesai,
                saldo_awal,
                saldo_akhir,
                len(rows),
            ),
        ).lastrowid
        for idx, (tgl, waktu, uraian, tipe, nominal, saldo, status) in enumerate(rows):
            mid = conn.execute(
                """
                INSERT INTO mutasi_bank (
                    batch_id, rekening_id, no_rekening, tanggal, waktu,
                    uraian, tipe, nominal, saldo, dedup_signature, status_rekonsiliasi
                ) VALUES (?, ?, '123', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    rekening_id,
                    tgl,
                    waktu,
                    uraian,
                    tipe,
                    nominal,
                    saldo,
                    f"{file_hash}_{idx}",
                    status,
                ),
            ).lastrowid
            mut_ids.append(int(mid))
        conn.commit()
    return mut_ids


def test_rbac_isolation_for_rekonsiliasi_endpoints(client: TestClient) -> None:
    staff_headers = _login(client, "staff", "staff123")
    assert client.get("/api/v1/rekonsiliasi/metadata", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/rekonsiliasi/report?rekening_id=1&month=2026-01", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/rekonsiliasi/export?rekening_id=1&month=2026-01", headers=staff_headers).status_code == 403
    assert client.post("/api/v1/rekonsiliasi/auto-run", headers=staff_headers).status_code == 403

    # Role with ONLY 'rekonsiliasi' (without 'input_struk' or 'input_mutasi') must still work
    with get_connection() as conn:
        conn.execute("INSERT INTO roles (name) VALUES ('auditor')")
        role_id = conn.execute("SELECT id FROM roles WHERE name = 'auditor'").fetchone()["id"]
        conn.execute("INSERT INTO role_menus (role_id, menu_key) VALUES (?, 'rekonsiliasi')", (role_id,))
        from app.core.password import hash_password

        conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role_id) VALUES ('auditor', 'Auditor', ?, ?)",
            (hash_password("audit123"), role_id),
        )
        conn.commit()

    auditor_headers = _login(client, "auditor", "audit123")
    assert client.get("/api/v1/struk/recent", headers=auditor_headers).status_code == 403
    assert client.get("/api/v1/mutasi/batches", headers=auditor_headers).status_code == 403
    meta_res = client.get("/api/v1/rekonsiliasi/metadata", headers=auditor_headers)
    assert meta_res.status_code == 200
    assert len(meta_res.json()["rekening_perusahaan"]) == 5


def test_bri_accounts_separated_and_over_100_transactions_not_truncated(client: TestClient) -> None:
    ids = _master_ids()
    accs = ids["accs"]
    cats = ids["cats"]
    fin_id = ids["users"]["finance"]

    # Insert 115 transactions in 2026-01 on BNI and 1 on BRI Operasional
    for i in range(115):
        _insert_tx(
            user_id=fin_id,
            nama_admin="Tim Finance",
            tanggal_transaksi=f"2026-01-{(i % 28) + 1:02d}",
            rekening_sumber_id=accs["BNI"],
            tipe="KELUAR",
            kategori_id=cats["Bahan Baku"],
            keterangan=f"Belanja #{i}",
            nominal_pokok=1000,
            total_mutasi=1000,
        )
    # Also insert newer transactions in 2026-02 that would push January out of /struk/recent?limit=100
    for i in range(15):
        _insert_tx(
            user_id=fin_id,
            nama_admin="Tim Finance",
            tanggal_transaksi="2026-02-05",
            rekening_sumber_id=accs["BNI"],
            tipe="MASUK",
            kategori_id=cats["Pendapatan Usaha (Penjualan Lainnya)"],
            keterangan=f"Feb #{i}",
            nominal_pokok=5000,
            total_mutasi=5000,
        )
    # BRI Operasional transaction must NOT appear in BRI (BritAma) report
    _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-12",
        rekening_sumber_id=accs["BRI Operasional"],
        tipe="KELUAR",
        kategori_id=cats["Biaya-Operasional"],
        keterangan="Belanja BRImo",
        nominal_pokok=350325,
        total_mutasi=350325,
    )

    headers = _login(client)
    meta = client.get("/api/v1/rekonsiliasi/metadata", headers=headers).json()
    kode_list = [r["kode_akun"] for r in meta["rekening_perusahaan"]]
    assert "BRI" in kode_list
    assert "BRI Operasional" in kode_list

    bni_jan = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={accs['BNI']}&month=2026-01",
        headers=headers,
    ).json()
    assert len(bni_jan["rows"]) == 115
    assert bni_jan["total_kredit"] == 115000

    bri_jan = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={accs['BRI']}&month=2026-01",
        headers=headers,
    ).json()
    assert bri_jan["rows"] == []

    brimo_jan = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={accs['BRI Operasional']}&month=2026-01",
        headers=headers,
    ).json()
    assert len(brimo_jan["rows"]) == 1
    assert brimo_jan["total_kredit"] == 350325


def test_cash_report_column_mapping_and_excel_export(client: TestClient) -> None:
    ids = _master_ids()
    accs = ids["accs"]
    cats = ids["cats"]
    fin_id = ids["users"]["finance"]

    _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-02",
        waktu_transaksi="10:00:00",
        rekening_sumber_id=accs["BNI"],
        tipe="MASUK",
        kategori_id=cats["Pendapatan Usaha (Penjualan Lainnya)"],
        penerima_pengirim="Toko Maju",
        keterangan="Penjualan",
        nominal_pokok=500000.50,
        total_mutasi=500000.50,
    )
    _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-03",
        waktu_transaksi="11:00:00",
        rekening_sumber_id=accs["BNI"],
        tipe="KELUAR",
        kategori_id=cats["Bahan Baku"],
        penerima_pengirim="Supplier X",
        keterangan="Beli Tepung",
        nominal_pokok=100000.25,
        total_mutasi=100000.25,
    )
    _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-04",
        waktu_transaksi="12:00:00",
        rekening_sumber_id=accs["BNI"],
        rekening_tujuan_id=accs["BRI Operasional"],
        tipe="PINDAH_BUKU",
        kategori_id=cats["Transfer Antar Rekening (Pindah Buku)"],
        penerima_pengirim="BRI Operasional",
        keterangan="Isi saldo BRImo",
        nominal_pokok=200000,
        biaya_admin=394,
        total_mutasi=200394,
    )

    headers = _login(client)
    rep = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={accs['BNI']}&month=2026-01",
        headers=headers,
    ).json()

    r_masuk, r_keluar, r_pb = rep["rows"]
    assert r_masuk["uang_masuk"] == "BNI"
    assert r_masuk["uang_keluar"] == ""
    assert r_masuk["debet"] == 500000.50

    assert r_keluar["uang_masuk"] == ""
    assert r_keluar["uang_keluar"] == "BNI"
    assert r_keluar["kredit"] == 100000.25

    assert r_pb["uang_masuk"] == "BRI Operasional"
    assert r_pb["uang_keluar"] == "BNI"
    assert r_pb["kredit"] == 200394

    # On BRI Operasional, incoming side shows DEBET = nominal_pokok (200000)
    rep_brimo = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={accs['BRI Operasional']}&month=2026-01",
        headers=headers,
    ).json()
    assert len(rep_brimo["rows"]) == 1
    assert rep_brimo["rows"][0]["debet"] == 200000
    assert rep_brimo["rows"][0]["uang_masuk"] == "BRI Operasional"
    assert rep_brimo["rows"][0]["uang_keluar"] == "BNI"

    # Excel export with saldo_awal override
    xlsx_res = client.get(
        f"/api/v1/rekonsiliasi/export?rekening_id={accs['BNI']}&month=2026-01&saldo_awal=1000000.25",
        headers=headers,
    )
    assert xlsx_res.status_code == 200
    assert "spreadsheetml.sheet" in xlsx_res.headers["content-type"]

    wb = load_workbook(BytesIO(xlsx_res.content), data_only=False)
    ws = wb.active
    assert ws.cell(6, 3).value == "Saldo Awal"
    assert ws.cell(6, 5).value is None
    assert ws.cell(6, 6).value is None
    assert ws.cell(6, 7).value == 1000000.25
    assert ws.cell(6, 9).value == "=G6"
    assert ws.cell(7, 5).value == "BNI"
    assert ws.cell(7, 6).value is None
    assert ws.cell(8, 5).value is None
    assert ws.cell(8, 6).value == "BNI"
    assert ws.cell(9, 5).value == "BRI Operasional"
    assert ws.cell(9, 6).value == "BNI"
    assert ws.cell(10, 7).value == "=SUM(G6:G9)"
    assert ws.cell(11, 8).value == "=G10-H10"
    assert ws.cell(12, 7).value == "=G10"
    assert ws.cell(12, 8).value == "=H10+H11"
    assert ws.cell(7, 1).alignment.wrap_text is True
    assert ws.cell(7, 4).alignment.wrap_text is True
    # Footer D-F must NOT have Rupiah number format
    assert ws.cell(10, 4).number_format == "General"

    # Cached formula values (<v>) must be populated for Excel Protected View / previews
    ws_val = load_workbook(BytesIO(xlsx_res.content), data_only=True).active
    assert ws_val.cell(6, 9).value == 1000000.25
    assert ws_val.cell(7, 9).value == 1500000.75
    assert ws_val.cell(8, 9).value == 1400000.5
    assert ws_val.cell(9, 9).value == 1199606.5
    assert ws_val.cell(10, 7).value == 1500000.75
    assert ws_val.cell(10, 8).value == 300394.25
    assert ws_val.cell(11, 8).value == 1199606.5
    assert ws_val.cell(12, 7).value == 1500000.75
    assert ws_val.cell(12, 8).value == 1500000.75


def test_multi_month_mutasi_reverse_tie_and_partial_warning(client: TestClient) -> None:
    ids = _master_ids()
    bni_id = ids["accs"]["BNI"]
    fin_id = ids["users"]["finance"]

    # Batch spanning Jan-Mar 2026; Feb has two rows at 00:00:00 inserted in reverse order
    _insert_mutasi_batch(
        rekening_id=bni_id,
        user_id=fin_id,
        nama_file="Q1_BNI.pdf",
        file_hash="h_q1",
        periode_mulai="2026-01-01",
        periode_selesai="2026-03-31",
        saldo_awal=1000000.0,
        saldo_akhir=1400000.25,
        rows=[
            ("2026-01-15", "10:00:00", "Masuk Jan", "CR", 200000.0, 1200000.0, "BELUM_TERCATAT"),
            # Intentionally reverse order on same timestamp 2026-02-10 00:00:00:
            # True chronology: +300000 -> 1500000, then -150000 -> 1350000
            ("2026-02-10", "00:00:00", "Keluar Feb", "DB", 150000.0, 1350000.0, "BELUM_TERCATAT"),
            ("2026-02-10", "00:00:00", "Masuk Feb", "CR", 300000.0, 1500000.0, "BELUM_TERCATAT"),
            ("2026-03-05", "09:00:00", "Masuk Mar", "CR", 50000.25, 1400000.25, "BELUM_TERCATAT"),
        ],
    )

    headers = _login(client)
    meta = client.get("/api/v1/rekonsiliasi/metadata", headers=headers).json()
    assert "2026-02" in meta["months"]

    feb = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={bni_id}&month=2026-02",
        headers=headers,
    ).json()
    assert feb["auto_saldo_awal"] == 1200000.0
    assert feb["saldo_akhir_bank"] == 1350000.0
    assert [m["uraian"] for m in feb["mutasi_rows"]] == ["Masuk Feb", "Keluar Feb"]

    # April (no mutasi yet) inherits March's ending balance 1400000.25
    apr = client.get(
        f"/api/v1/rekonsiliasi/report?rekening_id={bni_id}&month=2026-04",
        headers=headers,
    ).json()
    assert apr["auto_saldo_awal"] == 1400000.25


def test_manual_split_match_unmatch_and_penyesuaian_workflow(client: TestClient) -> None:
    ids = _master_ids()
    bni_id = ids["accs"]["BNI"]
    bri_id = ids["accs"]["BRI"]
    cats = ids["cats"]
    fin_id = ids["users"]["finance"]

    mut_ids = _insert_mutasi_batch(
        rekening_id=bni_id,
        user_id=fin_id,
        nama_file="BNI_Jan.pdf",
        file_hash="h_bni_jan",
        periode_mulai="2026-01-01",
        periode_selesai="2026-01-31",
        saldo_awal=1000000.0,
        saldo_akhir=1794500.0,
        rows=[
            ("2026-01-05", "10:00:00", "Transfer Vendor Split", "DB", 200000.0, 800000.0, "BELUM_TERCATAT"),
            ("2026-01-05", "10:00:01", "Biaya Transfer Bank", "DB", 6500.0, 793500.0, "BELUM_TERCATAT"),
            ("2026-01-20", "08:00:00", "Transfer Masuk Pindah Buku", "CR", 1000000.0, 1793500.0, "BELUM_TERCATAT"),
            ("2026-01-31", "23:59:59", "Interest on Account", "CR", 1000.0, 1794500.0, "BELUM_TERCATAT"),
        ],
    )
    tx_split = _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-05",
        rekening_sumber_id=bni_id,
        tipe="KELUAR",
        kategori_id=cats["Bahan Baku"],
        keterangan="Bayar Vendor",
        nominal_pokok=200000,
        biaya_admin=6500,
        total_mutasi=206500,
    )
    tx_pb = _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-20",
        rekening_sumber_id=bri_id,
        rekening_tujuan_id=bni_id,
        tipe="PINDAH_BUKU",
        kategori_id=cats["Transfer Antar Rekening (Pindah Buku)"],
        keterangan="Topup BNI dari BRI",
        nominal_pokok=1000000,
        total_mutasi=1000000,
    )

    headers = _login(client)

    # 1. Split admin manual match (1 tx -> 2 mutasi rows)
    split_res = client.post(
        "/api/v1/rekonsiliasi/match",
        headers=headers,
        json={"transaksi_id": tx_split, "mutasi_ids": [mut_ids[0], mut_ids[1]], "catatan": "Split admin"},
    )
    assert split_res.status_code == 200
    assert split_res.json()["jenis_match"] == "SPLIT_ADMIN"
    assert split_res.json()["status_rekonsiliasi"] == "SESUAI"
    group_id = split_res.json()["match_group_id"]

    # 2. Match 1 leg of PINDAH_BUKU when BRI statement isn't uploaded yet
    pb_res = client.post(
        "/api/v1/rekonsiliasi/match",
        headers=headers,
        json={"transaksi_id": tx_pb, "mutasi_ids": [mut_ids[2]]},
    )
    assert pb_res.status_code == 200
    assert pb_res.json()["status_rekonsiliasi"] == "PINDAH_BUKU_COCOK"

    # 3. Create PENYESUAIAN_MUTASI for bank interest (mut_ids[3])
    adj_res = client.post(
        "/api/v1/rekonsiliasi/penyesuaian",
        headers=headers,
        json={
            "mutasi_id": mut_ids[3],
            "kategori_id": cats["Pendapatan/Beban Lain"],
            "tipe": "MASUK",
            "penerima_pengirim": "Bank BNI",
            "keterangan": "Bunga Bank Januari",
        },
    )
    assert adj_res.status_code == 200
    adj_tx_id = adj_res.json()["transaksi_id"]

    rep = client.get(f"/api/v1/rekonsiliasi/report?rekening_id={bni_id}&month=2026-01", headers=headers).json()
    assert rep["is_balanced"] is True
    assert rep["selisih_saldo"] == 0.0
    assert rep["summary"]["mutasi_matched"] == 4
    assert rep["summary"]["tx_unmatched"] == 0

    # 4. Unmatch split match & delete penyesuaian
    assert client.delete(f"/api/v1/rekonsiliasi/match/{group_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/rekonsiliasi/penyesuaian/{adj_tx_id}", headers=headers).status_code == 200

    rep_after = client.get(f"/api/v1/rekonsiliasi/report?rekening_id={bni_id}&month=2026-01", headers=headers).json()
    assert rep_after["summary"]["mutasi_matched"] == 1  # only tx_pb remains matched
    assert rep_after["summary"]["tx_unmatched"] == 1


def test_auto_run_partial_warning_and_file_serving(client: TestClient) -> None:
    ids = _master_ids()
    bni_id = ids["accs"]["BNI"]
    cats = ids["cats"]
    fin_id = ids["users"]["finance"]

    # Partial month mutasi starting Jan 10 while tx exists on Jan 02
    _insert_mutasi_batch(
        rekening_id=bni_id,
        user_id=fin_id,
        nama_file="BNI_Partial.pdf",
        file_hash="h_partial",
        periode_mulai="2026-01-10",
        periode_selesai="2026-01-20",
        saldo_awal=500000.0,
        saldo_akhir=450000.0,
        rows=[
            ("2026-01-12", "09:00:00", "QRIS Toko Z", "DB", 50000.0, 450000.0, "BELUM_REKON"),
        ],
    )
    _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-02",
        rekening_sumber_id=bni_id,
        tipe="KELUAR",
        kategori_id=cats["Bahan Baku"],
        keterangan="Sebelum periode mutasi",
        nominal_pokok=10000,
        total_mutasi=10000,
    )
    tx_match_id = _insert_tx(
        user_id=fin_id,
        nama_admin="Tim Finance",
        tanggal_transaksi="2026-01-12",
        rekening_sumber_id=bni_id,
        tipe="KELUAR",
        kategori_id=cats["Bahan Baku"],
        keterangan="Toko Z",
        nominal_pokok=50000,
        total_mutasi=50000,
    )

    files_dir = Path(settings.storage_dir) / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / "proof_test.jpg").write_bytes(b"fake-jpg-bytes")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename, file_hash, jenis_struk, status_file
            ) VALUES (?, 'A', 'proof_test.jpg', 'orig.jpg', 'hash_proof_1', 'qris', 'TERPAKAI_UTAMA')
            """,
            (tx_match_id,),
        )
        conn.commit()

    headers = _login(client)
    auto_res = client.post("/api/v1/rekonsiliasi/auto-run", headers=headers, json={"rekening_id": bni_id})
    assert auto_res.status_code == 200
    assert auto_res.json()["matched_transactions"] == 1

    rep = client.get(f"/api/v1/rekonsiliasi/report?rekening_id={bni_id}&month=2026-01", headers=headers).json()
    assert rep["warnings"], "Expected partial-month coverage warning when earlier transaction exists"

    file_res = client.get("/api/v1/rekonsiliasi/files/proof_test.jpg", headers=headers)
    assert file_res.status_code == 200
    assert file_res.content == b"fake-jpg-bytes"
    assert client.get("/api/v1/rekonsiliasi/files/..%2Fsecret.txt", headers=headers).status_code == 404

