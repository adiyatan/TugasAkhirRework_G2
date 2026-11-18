import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app
from app.services import storage
import app.services.struk_service as struk_service_module


@pytest.fixture(autouse=True)
def isolated_struk_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "struk.db"))
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(settings, "vision_model", "gemini/gemini-2.5-flash")
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def vision(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "response": None}

    async def fake_complete_vision(**kwargs: Any) -> str:
        state["calls"].append(kwargs)
        return json.dumps(state["response"])

    monkeypatch.setattr(struk_service_module, "complete_vision", fake_complete_vision)
    return state


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
            "bni": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"],
            "bri": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BRI'").fetchone()["id"],
            "bahan": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"],
            "gaji": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Biaya-Gaji Karyawan'").fetchone()["id"],
            "pindah": conn.execute(
                "SELECT id FROM kategori_sop WHERE nama_kategori = 'Transfer Antar Rekening (Pindah Buku)'"
            ).fetchone()["id"],
            "operasional": conn.execute(
                "SELECT id FROM kategori_sop WHERE nama_kategori = 'Biaya-Operasional'"
            ).fetchone()["id"],
        }


def _file(
    *,
    filename: str,
    amount: int,
    document_type: str,
    date: str,
    time: str,
    sender_digits: str | None = None,
    recipient_digits: str | None = None,
    company_account: str | None = None,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "document_type": document_type,
        "amount": amount,
        "date": date,
        "time": time,
        "sender_digits": sender_digits,
        "recipient_digits": recipient_digits,
        "company_account": company_account,
        "sender_excluded": False,
        "is_unpaid": False,
    }


def _payload(
    *,
    slot_a: list[dict[str, Any]],
    slot_b: list[dict[str, Any]] | None = None,
    total: int,
    nominal: int,
    tipe: str = "KELUAR",
    kategori: str = "Bahan Baku",
    rekening: str = "BNI",
    rekening_tujuan: str | None = None,
    tanggal: str = "2026-01-09",
    waktu: str = "14:10:00",
) -> dict[str, Any]:
    return {
        "tanggal_transaksi": tanggal,
        "waktu_transaksi": waktu,
        "rekening": rekening,
        "rekening_tujuan": rekening_tujuan,
        "tipe": tipe,
        "kategori": kategori,
        "penerima_pengirim": "Penerima",
        "keterangan": "Pembelian",
        "nominal_pokok": nominal,
        "biaya_admin_kode_unik": total - nominal,
        "total_mutasi": total,
        "jenis_struk": "bank_transfer",
        "slot_a": slot_a,
        "slot_b": slot_b or [],
        "slot_c": [],
        "notes": "",
    }


def _post(
    client: TestClient,
    headers: dict[str, str],
    *,
    tab_type: str,
    slots: dict[str, list[tuple[str, bytes]]],
):
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for slot, values in slots.items():
        for filename, data in values:
            files.append((f"slot_{slot.lower()}", (filename, data, "image/jpeg")))
    return client.post(
        "/api/v1/struk/extract",
        headers=headers,
        data={"tab_type": tab_type, "is_cash": "false"},
        files=files,
    )


def _save_body(extract_body: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    extracted = extract_body["extracted"]
    body = {
        "staging_id": extract_body["staging_id"],
        "tanggal_transaksi": extracted["tanggal_transaksi"],
        "waktu_transaksi": extracted["waktu_transaksi"],
        "rekening_sumber_id": extracted["rekening_sumber_id"],
        "rekening_tujuan_id": extracted.get("rekening_tujuan_id"),
        "tipe": extracted["tipe"],
        "kategori_id": extracted["kategori_id"],
        "penerima_pengirim": extracted["penerima_pengirim"],
        "keterangan": extracted["keterangan"],
        "nominal_pokok": extracted["nominal_pokok"],
        "biaya_admin_kode_unik": extracted["biaya_admin_kode_unik"],
        "total_mutasi": extracted["total_mutasi"],
        "force_save_duplicate": False,
    }
    body.update(overrides)
    return body


def _counts() -> tuple[int, int]:
    with get_connection() as conn:
        return (
            conn.execute("SELECT COUNT(*) FROM transaksi_internal").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM file_bukti_log").fetchone()[0],
        )


def test_acceptance_flip_1a_3b_is_one_transaction_and_four_files(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="a.jpg",
                amount=2700329,
                document_type="flip_bank_to_fliptech",
                date="2026-01-09",
                time="14:10:00",
                sender_digits="1783680837",
                company_account="BNI",
            )
        ],
        slot_b=[
            _file(
                filename="b1.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                date="2026-01-09",
                time="14:12:00",
                recipient_digits="096",
            ),
            _file(
                filename="b2.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                date="2026-01-09",
                time="14:13:00",
                recipient_digits="777",
            ),
            _file(
                filename="b3.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                date="2026-01-09",
                time="14:14:00",
            ),
        ],
        total=2700329,
        nominal=2700000,
    )

    extracted = _post(
        client,
        headers,
        tab_type="flip",
        slots={
            "A": [("a.jpg", b"image-a")],
            "B": [("b1.jpg", b"image-b1"), ("b2.jpg", b"image-b2"), ("b3.jpg", b"image-b3")],
        },
    )
    assert extracted.status_code == 200
    saved = client.post("/api/v1/struk/save", headers=headers, json=_save_body(extracted.json()))

    assert saved.status_code == 200
    assert _counts() == (1, 4)
    with get_connection() as conn:
        files = conn.execute("SELECT slot, status_file FROM file_bukti_log ORDER BY slot, id").fetchall()
    assert [(row["slot"], row["status_file"]) for row in files] == [
        ("A", "TERPAKAI_UTAMA"),
        ("B", "TERPAKAI_PENDUKUNG_FLIP"),
        ("B", "TERPAKAI_PENDUKUNG_FLIP"),
        ("B", "TERPAKAI_PENDUKUNG_FLIP"),
    ]


def test_acceptance_duplicate_is_rejected_at_extract_and_save(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    ids = _ids()
    data = b"duplicate-image"
    digest = hashlib.sha256(data).hexdigest()
    storage.ensure_storage_layout()
    with get_connection() as conn:
        staff_id = conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, expires_at)
            VALUES ('stg_original', ?, 'normal', 0, 'SAVED', '[]', '2099-01-01T00:00:00')
            """,
            (staff_id,),
        )
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                staging_id, created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, total_mutasi
            ) VALUES ('stg_original', ?, 'Tim Staff', '2026-01-01', 'normal',
                '2026-01-01', '12:00:00', ?, 'KELUAR', ?, 75000)
            """,
            (staff_id, ids["bni"], ids["bahan"]),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename, file_hash,
                jenis_struk, status_file
            ) VALUES (?, 'A', 'original.jpg', 'original.jpg', ?, 'bank_transfer', 'TERPAKAI_UTAMA')
            """,
            (tx_id, digest),
        )
        conn.commit()

    extracted = _post(
        client,
        headers,
        tab_type="normal",
        slots={"A": [("copy.jpg", data)]},
    )
    assert extracted.status_code in {400, 409, 422}
    assert str(tx_id) in extracted.text

    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="copy.jpg",
                amount=75000,
                document_type="bank_transfer",
                date="2026-01-01",
                time="12:00:00",
                sender_digits="1783680837",
                company_account="BNI",
            )
        ],
        total=75000,
        nominal=75000,
    )
    staging_id = "stg_duplicate_save"
    manifest = [
        {
            "slot": "A",
            "filename": "copy.jpg",
            "orig_filename": "copy.jpg",
            "content_type": "image/jpeg",
            "size": len(data),
            "sha256": digest,
            "stored_name": "copy.jpg",
            "document_type": "bank_transfer",
            "amount": 75000,
            "date": "2026-01-01",
            "time": "12:00:00",
        }
    ]
    storage.write_staging_file(staging_id, "copy.jpg", data)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, expires_at)
            VALUES (?, ?, 'normal', 0, 'OPEN', ?, '2099-01-01T00:00:00')
            """,
            (
                staging_id,
                staff_id,
                json.dumps(manifest),
            ),
        )
        conn.commit()
    saved = client.post(
        "/api/v1/struk/save",
        headers=headers,
        json={
            "staging_id": staging_id,
            "tanggal_transaksi": "2026-01-01",
            "waktu_transaksi": "12:00:00",
            "rekening_sumber_id": ids["bni"],
            "rekening_tujuan_id": None,
            "tipe": "KELUAR",
            "kategori_id": ids["bahan"],
            "nominal_pokok": 75000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 75000,
        },
    )
    assert saved.status_code == 409
    assert str(tx_id) in saved.text
    assert _counts() == (1, 1)


def test_acceptance_double_save_creates_one_transaction(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="a.jpg",
                amount=75000,
                document_type="bank_transfer",
                date="2026-01-09",
                time="14:10:00",
                sender_digits="1783680837",
                company_account="BNI",
            )
        ],
        total=75000,
        nominal=75000,
    )
    extracted = _post(client, headers, tab_type="normal", slots={"A": [("a.jpg", b"image-a")]})
    body = _save_body(extracted.json())

    first = client.post("/api/v1/struk/save", headers=headers, json=body)
    second = client.post("/api/v1/struk/save", headers=headers, json=body)

    assert first.status_code == 200
    assert second.status_code == 409
    assert _counts() == (1, 1)


def test_acceptance_slip_and_reimburse_use_slot_b_datetime(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    ids = _ids()

    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="slip.jpg",
                amount=1128750,
                document_type="slip_gaji",
                date="2025-12-31",
                time="23:59:59",
            )
        ],
        slot_b=[
            _file(
                filename="transfer-a.jpg",
                amount=1129075,
                document_type="flip_bank_to_fliptech",
                date="2026-01-02",
                time="10:00:00",
                sender_digits="1783680837",
                company_account="BNI",
            ),
            _file(
                filename="transfer-b.jpg",
                amount=1128750,
                document_type="flip_to_recipient",
                date="2026-01-02",
                time="10:05:00",
            ),
        ],
        total=1129075,
        nominal=1128750,
        kategori="Biaya-Gaji Karyawan",
    )
    slip = _post(
        client,
        headers,
        tab_type="slip_gaji",
        slots={"A": [("slip.jpg", b"slip")], "B": [("transfer-a.jpg", b"ta"), ("transfer-b.jpg", b"tb")]},
    )
    assert slip.status_code == 200
    assert slip.json()["extracted"]["tanggal_transaksi"] == "2026-01-02"
    assert slip.json()["extracted"]["waktu_transaksi"] == "10:00:00"
    saved_slip = client.post("/api/v1/struk/save", headers=headers, json=_save_body(slip.json()))
    assert saved_slip.status_code == 200

    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="nota.jpg",
                amount=75000,
                document_type="qris_receipt",
                date="2026-01-17",
                time="09:28:30",
            )
        ],
        slot_b=[
            _file(
                filename="reimburse.jpg",
                amount=75000,
                document_type="bank_transfer",
                date="2026-01-17",
                time="10:40:46",
                sender_digits="1783680837",
                company_account="BNI",
            )
        ],
        total=75000,
        nominal=75000,
        kategori="Biaya-Operasional",
    )
    reimburse = _post(
        client,
        headers,
        tab_type="reimburse",
        slots={"A": [("nota.jpg", b"nota")], "B": [("reimburse.jpg", b"reimburse")]},
    )
    assert reimburse.status_code == 200
    assert reimburse.json()["extracted"]["tanggal_transaksi"] == "2026-01-17"
    assert reimburse.json()["extracted"]["waktu_transaksi"] == "10:40:46"
    assert reimburse.json()["extracted"]["rekening_sumber_id"] == ids["bni"]
    saved_reimburse = client.post(
        "/api/v1/struk/save", headers=headers, json=_save_body(reimburse.json())
    )
    assert saved_reimburse.status_code == 200

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tanggal_transaksi, waktu_transaksi FROM transaksi_internal ORDER BY id"
        ).fetchall()
    assert [(row["tanggal_transaksi"], row["waktu_transaksi"]) for row in rows] == [
        ("2026-01-02", "10:00:00"),
        ("2026-01-17", "10:40:46"),
    ]


def test_acceptance_pindah_buku_sets_source_and_destination(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    ids = _ids()
    vision["response"] = _payload(
        slot_a=[
            _file(
                filename="transfer.jpg",
                amount=1000000,
                document_type="bank_transfer",
                date="2026-01-09",
                time="14:10:00",
                sender_digits="1783680837",
                recipient_digits="306601000009566",
                company_account="BNI",
            )
        ],
        total=1000000,
        nominal=1000000,
    )
    extracted = _post(client, headers, tab_type="normal", slots={"A": [("transfer.jpg", b"transfer")]})
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["extracted"]["tipe"] == "PINDAH_BUKU"
    assert body["extracted"]["rekening_sumber_id"] == ids["bni"]
    assert body["extracted"]["rekening_tujuan_id"] == ids["bri"]
    assert body["extracted"]["kategori_id"] == ids["pindah"]

    saved = client.post("/api/v1/struk/save", headers=headers, json=_save_body(body))
    assert saved.status_code == 200
    with get_connection() as conn:
        tx = conn.execute("SELECT rekening_sumber_id, rekening_tujuan_id, tipe FROM transaksi_internal").fetchone()
    assert tx["rekening_sumber_id"] == ids["bni"]
    assert tx["rekening_tujuan_id"] == ids["bri"]
    assert tx["tipe"] == "PINDAH_BUKU"
