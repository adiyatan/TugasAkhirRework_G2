import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app
from app.services import storage


@pytest.fixture(autouse=True)
def isolated_struk_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "struk.db"))
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str = "staff", password: str = "staff123") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ids() -> dict[str, int]:
    with get_connection() as conn:
        return {
            "staff": conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()["id"],
            "finance": conn.execute("SELECT id FROM users WHERE username = 'finance'").fetchone()["id"],
            "bni": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"],
            "bri": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BRI'").fetchone()["id"],
            "bahan": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"],
            "gaji": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Biaya-Gaji Karyawan'").fetchone()["id"],
        }


def _default_extracted(*, tab_type: str = "flip", date: str = "2026-01-09", time: str = "14:10:00") -> dict[str, Any]:
    ids = _ids()
    return {
        "tanggal_transaksi": date,
        "waktu_transaksi": time,
        "rekening": "BNI",
        "rekening_tujuan": None,
        "tipe": "KELUAR",
        "kategori": "Bahan Baku",
        "penerima_pengirim": "Penerima",
        "keterangan": "Pembelian bahan baku",
        "nominal_pokok": 2700000,
        "biaya_admin_kode_unik": 329,
        "total_mutasi": 2700329,
        "jenis_struk": "flip_bank_to_fliptech",
        "rekening_sumber_id": ids["bni"],
        "rekening_tujuan_id": None,
        "kategori_id": ids["bahan"],
        "slot_a": [],
        "slot_b": [],
        "slot_c": [],
        "notes": "",
        "tab_type": tab_type,
    }


def _make_staging(
    *,
    staging_id: str = "stg_save_test",
    tab_type: str = "flip",
    status: str = "OPEN",
    username: str = "staff",
    expires_at: str | None = None,
    file_specs: list[dict[str, Any]] | None = None,
    extracted: dict[str, Any] | None = None,
) -> str:
    ids = _ids()
    specs = file_specs or [
        {"slot": "A", "filename": "a.jpg", "data": b"image-a", "amount": 2700329, "document_type": "flip_bank_to_fliptech"},
        {"slot": "B", "filename": "b1.jpg", "data": b"image-b1", "amount": 900000, "document_type": "flip_to_recipient"},
        {"slot": "B", "filename": "b2.jpg", "data": b"image-b2", "amount": 900000, "document_type": "flip_to_recipient"},
        {"slot": "B", "filename": "b3.jpg", "data": b"image-b3", "amount": 900000, "document_type": "flip_to_recipient"},
    ]
    manifest = []
    for spec in specs:
        digest = hashlib.sha256(spec["data"]).hexdigest()
        stored_name = storage.safe_stored_filename(spec["filename"], digest, spec["slot"])
        storage.write_staging_file(staging_id, stored_name, spec["data"])
        manifest.append(
            {
                "slot": spec["slot"],
                "filename": spec["filename"],
                "orig_filename": spec["filename"],
                "content_type": "image/jpeg",
                "size": len(spec["data"]),
                "sha256": digest,
                "stored_name": stored_name,
                "document_type": spec["document_type"],
                "amount": spec["amount"],
                "date": "2026-01-09",
                "time": "14:10:00",
            }
        )
    if expires_at is None:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_staging (
                id, user_id, tab_type, is_cash, status, manifest_json,
                extracted_json, expires_at
            ) VALUES (?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                staging_id,
                ids[username],
                tab_type,
                status,
                json.dumps(manifest),
                json.dumps(extracted or _default_extracted(tab_type=tab_type)),
                expires_at,
            ),
        )
        conn.commit()
    return staging_id


def _body(staging_id: str, **overrides: Any) -> dict[str, Any]:
    ids = _ids()
    body = {
        "staging_id": staging_id,
        "tanggal_transaksi": "2026-01-09",
        "waktu_transaksi": "14:10:00",
        "rekening_sumber_id": ids["bni"],
        "rekening_tujuan_id": None,
        "tipe": "KELUAR",
        "kategori_id": ids["bahan"],
        "penerima_pengirim": "Penerima",
        "keterangan": "Pembelian bahan baku",
        "nominal_pokok": 2700000,
        "biaya_admin_kode_unik": 329,
        "total_mutasi": 2700329,
        "force_save_duplicate": False,
    }
    body.update(overrides)
    return body


def _save(client: TestClient, headers: dict[str, str], body: dict[str, Any]):
    return client.post("/api/v1/struk/save", headers=headers, json=body)


def _counts() -> tuple[int, int]:
    with get_connection() as conn:
        return (
            conn.execute("SELECT COUNT(*) FROM transaksi_internal").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM file_bukti_log").fetchone()[0],
        )


def test_save_requires_authentication(client: TestClient) -> None:
    staging_id = _make_staging()

    response = _save(client, {}, _body(staging_id))

    assert response.status_code == 401
    assert _counts() == (0, 0)


def test_save_unknown_staging_is_rejected(client: TestClient) -> None:
    headers = _login(client)

    response = _save(client, headers, _body("stg_missing"))

    assert response.status_code in {404, 409}
    assert _counts() == (0, 0)


def test_save_expired_staging_is_rejected(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging(expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())

    response = _save(client, headers, _body(staging_id))

    assert response.status_code == 409
    assert "kedaluwarsa" in response.text.lower()
    assert _counts() == (0, 0)


def test_save_foreign_staging_is_rejected_for_staff(client: TestClient) -> None:
    headers = _login(client, "staff", "staff123")
    staging_id = _make_staging(username="finance")

    response = _save(client, headers, _body(staging_id))

    assert response.status_code == 403
    assert _counts() == (0, 0)


def test_save_already_saved_staging_is_rejected(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging(status="SAVED")

    response = _save(client, headers, _body(staging_id))

    assert response.status_code == 409
    assert _counts() == (0, 0)


def test_save_flip_creates_one_transaction_and_four_files(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging()

    response = _save(client, headers, _body(staging_id))

    assert response.status_code == 200
    body = response.json()
    assert body["staging_id"] == staging_id
    assert body["transaksi_id"] > 0
    assert _counts() == (1, 4)

    with get_connection() as conn:
        tx = conn.execute("SELECT * FROM transaksi_internal").fetchone()
        assert tx["staging_id"] == staging_id
        assert tx["nama_admin"] == "Tim Staff"
        assert tx["sumber_pencatatan"] == "INPUT_STRUK"
        assert tx["tab_type"] == "flip"
        assert tx["total_mutasi"] == 2700329
        files = conn.execute("SELECT * FROM file_bukti_log ORDER BY slot, id").fetchall()
        assert [row["slot"] for row in files] == ["A", "B", "B", "B"]
        assert [row["status_file"] for row in files] == [
            "TERPAKAI_UTAMA",
            "TERPAKAI_PENDUKUNG_FLIP",
            "TERPAKAI_PENDUKUNG_FLIP",
            "TERPAKAI_PENDUKUNG_FLIP",
        ]
        assert all(Path(settings.storage_dir, "files", row["filename"]).is_file() for row in files)
        staging = conn.execute("SELECT status FROM upload_staging WHERE id = ?", (staging_id,)).fetchone()
        assert staging["status"] == "SAVED"


def test_save_twice_creates_only_one_transaction(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging()
    body = _body(staging_id)

    first = _save(client, headers, body)
    second = _save(client, headers, body)

    assert first.status_code == 200
    assert second.status_code == 409
    assert _counts() == (1, 4)


def test_save_rechecks_file_hash_and_references_original(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging()
    ids = _ids()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, expires_at)
            VALUES ('stg_old', ?, 'normal', 0, 'SAVED', '[]', '2099-01-01T00:00:00')
            """,
            (ids["staff"],),
        )
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                staging_id, created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, total_mutasi
            ) VALUES ('stg_old', ?, 'Tim Staff', '2026-01-01', 'normal',
                '2026-01-01', '12:00:00', ?, 'KELUAR', ?, 1000)
            """,
            (ids["staff"], ids["bni"], ids["bahan"]),
        ).lastrowid
        manifest = json.loads(
            conn.execute("SELECT manifest_json FROM upload_staging WHERE id = ?", (staging_id,)).fetchone()[0]
        )
        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename, file_hash,
                jenis_struk, status_file
            ) VALUES (?, 'A', 'old.jpg', 'old.jpg', ?, 'bank_transfer', 'TERPAKAI_UTAMA')
            """,
            (tx_id, manifest[0]["sha256"]),
        )
        conn.commit()

    response = _save(client, headers, _body(staging_id))

    assert response.status_code == 409
    assert str(tx_id) in response.text
    assert _counts() == (1, 1)


def test_save_validates_account_and_category(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging()

    bad_account = _save(client, headers, _body(staging_id, rekening_sumber_id=99999))
    assert bad_account.status_code in {400, 422}

    bad_category = _save(client, headers, _body(staging_id, kategori_id=99999))
    assert bad_category.status_code in {400, 422}
    assert _counts() == (0, 0)


def test_save_pindah_buku_requires_distinct_destination(client: TestClient) -> None:
    headers = _login(client)
    ids = _ids()
    staging_id = _make_staging()

    missing = _save(client, headers, _body(staging_id, tipe="PINDAH_BUKU", rekening_sumber_id=ids["bni"]))
    assert missing.status_code in {400, 422}

    same = _save(
        client,
        headers,
        _body(
            staging_id,
            tipe="PINDAH_BUKU",
            rekening_sumber_id=ids["bni"],
            rekening_tujuan_id=ids["bni"],
        ),
    )
    assert same.status_code in {400, 422}
    assert _counts() == (0, 0)


def test_save_rejects_locked_field_changes(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging(
        tab_type="reimburse",
        extracted=_default_extracted(tab_type="reimburse", date="2026-01-17", time="10:40:46"),
    )

    response = _save(
        client,
        headers,
        _body(
            staging_id,
            tanggal_transaksi="2026-01-16",
            waktu_transaksi="09:00:00",
            nominal_pokok=2700000,
            total_mutasi=2700329,
        ),
    )

    assert response.status_code in {400, 422}
    assert "terkunci" in response.text.lower() or "slot b" in response.text.lower()
    assert _counts() == (0, 0)


def test_save_semantic_duplicate_requires_force(client: TestClient) -> None:
    headers = _login(client)
    ids = _ids()
    staging_id = _make_staging()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transaksi_internal (
                created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, total_mutasi
            ) VALUES (?, 'Tim Staff', '2026-01-01', 'normal',
                '2026-01-09', '12:00:00', ?, 'KELUAR', ?, 2700329)
            """,
            (ids["staff"], ids["bni"], ids["bahan"]),
        )
        conn.commit()

    blocked = _save(client, headers, _body(staging_id))
    assert blocked.status_code == 409
    assert _counts() == (1, 0)

    forced = _save(client, headers, _body(staging_id, force_save_duplicate=True))
    assert forced.status_code == 200
    assert _counts() == (2, 4)


def test_save_missing_staging_file_leaves_no_partial_rows(client: TestClient) -> None:
    headers = _login(client)
    staging_id = _make_staging()
    with get_connection() as conn:
        manifest = json.loads(
            conn.execute("SELECT manifest_json FROM upload_staging WHERE id = ?", (staging_id,)).fetchone()[0]
        )
    Path(settings.storage_dir, "staging", staging_id, manifest[0]["stored_name"]).unlink()

    response = _save(client, headers, _body(staging_id))

    assert response.status_code in {400, 409, 500}
    assert _counts() == (0, 0)
    with get_connection() as conn:
        status = conn.execute("SELECT status FROM upload_staging WHERE id = ?", (staging_id,)).fetchone()["status"]
    assert status == "OPEN"


def test_save_blocks_bypass_of_extract_rule_violations(client: TestClient) -> None:
    headers = _login(client)
    ids = _ids()

    # 1. Normal unpaid screenshot cannot be saved even with its staging_id
    unpaid_extracted = _default_extracted(tab_type="normal")
    unpaid_extracted.update(
        {
            "nominal_pokok": 75000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 75000,
            "slot_a": [{"is_unpaid": True, "document_type": "shopee_order", "amount": 75000}],
        }
    )
    stg_unpaid = _make_staging(
        tab_type="normal",
        file_specs=[{"slot": "A", "filename": "u.jpg", "data": b"u", "amount": 75000, "document_type": "shopee_order"}],
        extracted=unpaid_extracted,
    )
    res_unpaid = _save(
        client,
        headers,
        _body(stg_unpaid, nominal_pokok=75000, biaya_admin_kode_unik=0, total_mutasi=75000),
    )
    assert res_unpaid.status_code == 400
    assert "belum bayar" in res_unpaid.text.lower()

    # 2. Flip diff > 1000 cannot be saved
    flip_bad_extracted = _default_extracted(tab_type="flip")
    flip_bad_extracted.update({"nominal_pokok": 2700000, "biaya_admin_kode_unik": 5000, "total_mutasi": 2705000})
    stg_flip = _make_staging(
        staging_id="stg_flip_bad",
        tab_type="flip",
        file_specs=[
            {"slot": "A", "filename": "fa.jpg", "data": b"fa", "amount": 2705000, "document_type": "flip_bank_to_fliptech"},
            {"slot": "B", "filename": "fb.jpg", "data": b"fb", "amount": 2700000, "document_type": "flip_to_recipient"},
        ],
        extracted=flip_bad_extracted,
    )
    res_flip = _save(
        client,
        headers,
        _body(stg_flip, nominal_pokok=2700000, biaya_admin_kode_unik=5000, total_mutasi=2705000),
    )
    assert res_flip.status_code == 400
    assert "1.000" in res_flip.text

    # 3. Reimburse diff > 1000 cannot be saved
    reim_bad = _default_extracted(tab_type="reimburse")
    reim_bad.update(
        {
            "nominal_pokok": 75000,
            "biaya_admin_kode_unik": 25000,
            "total_mutasi": 100000,
            "slot_a": [{"amount": 75000}],
            "slot_b": [{"amount": 100000, "sender_excluded": False}],
        }
    )
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, extracted_json, expires_at)
            VALUES ('stg_reim_bad', ?, 'reimburse', 0, 'OPEN', '[]', ?, '2099-01-01T00:00:00')
            """,
            (ids["staff"], json.dumps(reim_bad)),
        )
        conn.commit()
    res_reim = _save(
        client,
        headers,
        _body("stg_reim_bad", nominal_pokok=75000, biaya_admin_kode_unik=25000, total_mutasi=100000),
    )
    assert res_reim.status_code == 400
    assert "1.000" in res_reim.text
    assert _counts() == (0, 0)


def test_save_flip_pindah_buku_locks_kategori_and_destination(client: TestClient) -> None:
    headers = _login(client)
    ids = _ids()
    with get_connection() as conn:
        pindah_id = conn.execute(
            "SELECT id FROM kategori_sop WHERE nama_kategori = 'Transfer Antar Rekening (Pindah Buku)'"
        ).fetchone()["id"]
    extracted = _default_extracted(tab_type="flip")
    extracted.update(
        {
            "tipe": "PINDAH_BUKU",
            "rekening_tujuan": "BRI",
            "rekening_tujuan_id": ids["bri"],
            "kategori": "Transfer Antar Rekening (Pindah Buku)",
            "kategori_id": pindah_id,
        }
    )
    staging_id = _make_staging(tab_type="flip", extracted=extracted)

    tampered = _save(
        client,
        headers,
        _body(
            staging_id,
            tipe="PINDAH_BUKU",
            rekening_tujuan_id=ids["bri"],
            kategori_id=ids["bahan"],
        ),
    )
    assert tampered.status_code == 400
    assert "terkunci" in tampered.text.lower()
    assert _counts() == (0, 0)
