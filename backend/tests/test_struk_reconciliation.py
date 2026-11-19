from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app
import app.services.struk_service as struk_service_module


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
            "bni": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"],
            "bri": conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BRI'").fetchone()["id"],
            "bahan": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"],
            "pindah": conn.execute(
                "SELECT id FROM kategori_sop WHERE nama_kategori = 'Transfer Antar Rekening (Pindah Buku)'"
            ).fetchone()["id"],
        }


def _seed_mutasi(*entries: tuple[int, str, str, int, str]) -> list[int]:
    ids = _ids()
    mutasi_ids: list[int] = []
    with get_connection() as conn:
        batch_id = conn.execute(
            """
            INSERT INTO mutasi_upload_batch (
                rekening_id, uploaded_by_user_id, nama_file, file_hash, metode_ekstraksi, jumlah_baris
            ) VALUES (?, ?, 'mutasi.pdf', 'batch_hash_1', 'test', ?)
            """,
            (ids["bni"], ids["staff"], len(entries)),
        ).lastrowid
        for idx, (rek_id, tanggal, tipe, nominal, uraian) in enumerate(entries):
            mut_id = conn.execute(
                """
                INSERT INTO mutasi_bank (
                    batch_id, rekening_id, no_rekening, tanggal, waktu,
                    uraian, tipe, nominal, saldo, dedup_signature
                ) VALUES (?, ?, '000', ?, '12:00:00', ?, ?, ?, 1000000, ?)
                """,
                (batch_id, rek_id, tanggal, uraian, tipe, nominal, f"sig_{idx}_{rek_id}_{nominal}"),
            ).lastrowid
            mutasi_ids.append(mut_id)
        conn.commit()
    return mutasi_ids


def _extract_and_save(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    *,
    vision_payload: dict[str, Any],
    image_bytes: bytes = b"img-data",
) -> Any:
    import json

    async def fake_complete_vision(**_: Any) -> str:
        return json.dumps(vision_payload)

    monkeypatch.setattr(struk_service_module, "complete_vision", fake_complete_vision)
    extracted = client.post(
        "/api/v1/struk/extract",
        headers=headers,
        data={"tab_type": "normal", "is_cash": "false"},
        files=[("slot_a", ("a.jpg", image_bytes, "image/jpeg"))],
    )
    assert extracted.status_code == 200
    body = extracted.json()["extracted"]
    return client.post(
        "/api/v1/struk/save",
        headers=headers,
        json={
            "staging_id": extracted.json()["staging_id"],
            "tanggal_transaksi": body["tanggal_transaksi"],
            "waktu_transaksi": body["waktu_transaksi"],
            "rekening_sumber_id": body["rekening_sumber_id"],
            "rekening_tujuan_id": body.get("rekening_tujuan_id"),
            "tipe": body["tipe"],
            "kategori_id": body["kategori_id"],
            "penerima_pengirim": body["penerima_pengirim"],
            "keterangan": body["keterangan"],
            "nominal_pokok": body["nominal_pokok"],
            "biaya_admin_kode_unik": body["biaya_admin_kode_unik"],
            "total_mutasi": body["total_mutasi"],
            "force_save_duplicate": False,
        },
    )


def test_save_auto_reconciles_exact_match_and_finance_delete_resets_mutasi(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _ids()
    mut_ids = _seed_mutasi((ids["bni"], "2026-01-09", "DB", 75000, "QRIS Toko A"))
    staff_headers = _login(client, "staff", "staff123")

    saved = _extract_and_save(
        client,
        monkeypatch,
        staff_headers,
        vision_payload={
            "tanggal_transaksi": "2026-01-09",
            "waktu_transaksi": "14:10:00",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Bahan Baku",
            "penerima_pengirim": "Toko A",
            "keterangan": "Belanja",
            "nominal_pokok": 75000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 75000,
            "jenis_struk": "qris_receipt",
            "slot_a": [
                {
                    "filename": "a.jpg",
                    "document_type": "qris_receipt",
                    "amount": 75000,
                    "date": "2026-01-09",
                    "time": "14:10:00",
                    "sender_digits": "1783680837",
                    "recipient_digits": None,
                    "company_account": "BNI",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_b": [],
            "slot_c": [],
            "notes": "",
        },
    )
    assert saved.status_code == 200
    data = saved.json()
    assert data["reconciliation"]["matched"] is True
    assert data["reconciliation"]["status_rekonsiliasi"] == "SESUAI"
    assert data["reconciliation"]["jenis_match"] == "EXACT"

    with get_connection() as conn:
        tx = conn.execute(
            "SELECT status_rekonsiliasi FROM transaksi_internal WHERE id = ?",
            (data["transaksi_id"],),
        ).fetchone()
        mut = conn.execute(
            "SELECT status_rekonsiliasi FROM mutasi_bank WHERE id = ?",
            (mut_ids[0],),
        ).fetchone()
        matches = conn.execute("SELECT jenis_match FROM rekonsiliasi_match").fetchall()
    assert tx["status_rekonsiliasi"] == "SESUAI"
    assert mut["status_rekonsiliasi"] == "SESUAI"
    assert [row["jenis_match"] for row in matches] == ["EXACT"]

    # Staff cannot delete already-reconciled transaction, finance can & mutasi resets
    assert client.delete(f"/api/v1/struk/{data['transaksi_id']}", headers=staff_headers).status_code == 403
    finance_headers = _login(client, "finance", "finance123")
    assert client.delete(f"/api/v1/struk/{data['transaksi_id']}", headers=finance_headers).status_code == 200
    with get_connection() as conn:
        mut_after = conn.execute(
            "SELECT status_rekonsiliasi FROM mutasi_bank WHERE id = ?",
            (mut_ids[0],),
        ).fetchone()
    assert mut_after["status_rekonsiliasi"] == "BELUM_REKON"


def test_save_auto_reconciles_tolerance_and_pindah_buku_pair(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _ids()
    mut_ids = _seed_mutasi(
        (ids["bni"], "2026-01-09", "DB", 800353, "Transfer Fliptech"),
        (ids["bni"], "2026-01-10", "DB", 1000000, "Pindah keluar"),
        (ids["bri"], "2026-01-10", "CR", 1000000, "Pindah masuk"),
    )
    headers = _login(client, "staff", "staff123")

    tol_saved = _extract_and_save(
        client,
        monkeypatch,
        headers,
        image_bytes=b"img-tol",
        vision_payload={
            "tanggal_transaksi": "2026-01-09",
            "waktu_transaksi": "14:10:00",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Bahan Baku",
            "penerima_pengirim": "Vendor X",
            "keterangan": "Belanja",
            "nominal_pokok": 800000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 800000,
            "jenis_struk": "bank_transfer",
            "slot_a": [
                {
                    "filename": "a.jpg",
                    "document_type": "bank_transfer",
                    "amount": 800000,
                    "date": "2026-01-09",
                    "time": "14:10:00",
                    "sender_digits": "1783680837",
                    "recipient_digits": None,
                    "company_account": "BNI",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_b": [],
            "slot_c": [],
            "notes": "",
        },
    )
    assert tol_saved.status_code == 200
    assert tol_saved.json()["reconciliation"]["status_rekonsiliasi"] == "SELISIH_KODE_UNIK_ADMIN"
    assert tol_saved.json()["reconciliation"]["jenis_match"] == "TOLERANCE"

    pb_saved = _extract_and_save(
        client,
        monkeypatch,
        headers,
        image_bytes=b"img-pb",
        vision_payload={
            "tanggal_transaksi": "2026-01-10",
            "waktu_transaksi": "09:00:00",
            "rekening": "BNI",
            "rekening_tujuan": "BRI",
            "tipe": "PINDAH_BUKU",
            "kategori": "Transfer Antar Rekening (Pindah Buku)",
            "penerima_pengirim": "BRI",
            "keterangan": "Pindah dana",
            "nominal_pokok": 1000000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 1000000,
            "jenis_struk": "bank_transfer",
            "slot_a": [
                {
                    "filename": "a.jpg",
                    "document_type": "bank_transfer",
                    "amount": 1000000,
                    "date": "2026-01-10",
                    "time": "09:00:00",
                    "sender_digits": "1783680837",
                    "recipient_digits": "306601000009566",
                    "company_account": "BNI",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_b": [],
            "slot_c": [],
            "notes": "",
        },
    )
    assert pb_saved.status_code == 200
    assert pb_saved.json()["reconciliation"]["status_rekonsiliasi"] == "PINDAH_BUKU_COCOK"
    assert pb_saved.json()["reconciliation"]["jenis_match"] == "PINDAH_BUKU_PAIR"
    assert set(pb_saved.json()["reconciliation"]["mutasi_ids"]) == {mut_ids[1], mut_ids[2]}
