import json
from pathlib import Path
from typing import Any

import fitz
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app
import app.services.mutasi_parser as mutasi_parser_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRI_PDF_PATH = PROJECT_ROOT / "Bukti_Terstruktur_Januari_2026" / "06_Mutasi_Rekening" / "Mutasi Rekening BRI-Januari 2026.pdf"
BNI_PDF_PATH = PROJECT_ROOT / "Bukti_Terstruktur_Januari_2026" / "06_Mutasi_Rekening" / "BNI_Mutasi_Januari_2026.pdf"


@pytest.fixture(autouse=True)
def isolated_mutasi_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "mutasi.db"))
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "max_upload_mb", 10)
    monkeypatch.setattr(settings, "vision_model", "gemini/gemini-2.5-flash")
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, username: str = "finance", password: str = "finance123") -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _account_ids() -> dict[str, int]:
    with get_connection() as conn:
        return {
            row["kode_akun"]: row["id"]
            for row in conn.execute("SELECT id, kode_akun FROM rekening_perusahaan").fetchall()
        }


def _make_vector_like_pdf(pages: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(20, 20, 100, 50))
        shape.finish()
        shape.commit()
    return doc.tobytes()


def test_staff_is_rejected_on_all_mutasi_endpoints(client: TestClient) -> None:
    staff_headers = _login(client, "staff", "staff123")

    assert client.get("/api/v1/mutasi/metadata", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/mutasi/batches", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/mutasi/rows", headers=staff_headers).status_code == 403
    assert client.delete("/api/v1/mutasi/batches/1", headers=staff_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/mutasi/preview",
            headers=staff_headers,
            files={"file": ("bri.pdf", b"%PDF-1.4\n", "application/pdf")},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/mutasi/save",
            headers=staff_headers,
            json={
                "rekening_id": 1,
                "nama_file": "bri.pdf",
                "file_hash": "a" * 64,
                "metode_ekstraksi": "Deterministik",
                "rows": [
                    {
                        "tanggal": "2026-01-07",
                        "waktu": "11:15:39",
                        "uraian": "MPN",
                        "tipe": "DB",
                        "nominal": 500000,
                        "saldo": 214031779,
                    }
                ],
            },
        ).status_code
        == 403
    )


def test_metadata_excludes_kas_operasional(client: TestClient) -> None:
    headers = _login(client, "finance", "finance123")
    res = client.get("/api/v1/mutasi/metadata", headers=headers)
    assert res.status_code == 200
    codes = [row["kode_akun"] for row in res.json()["rekening_perusahaan"]]
    assert "Kas Operasional" not in codes
    assert {"BNI", "BRI", "BRI Operasional", "Bank Jago"}.issubset(set(codes))

    # Explicitly selecting Kas Operasional in preview must fail
    kas_id = _account_ids()["Kas Operasional"]
    bad = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": str(kas_id)},
        files={"file": ("kas.pdf", _make_vector_like_pdf(1), "application/pdf")},
    )
    assert bad.status_code == 400


def test_bri_ibbiz_pdf_parsed_deterministically_without_ai_and_reconciles(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    vision_calls: list[Any] = []

    async def fail_if_called(**kwargs: Any) -> str:
        vision_calls.append(kwargs)
        raise AssertionError("Vision AI must not be called for BRI IBBIZ text PDF")

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fail_if_called)

    headers = _login(client, "finance", "finance123")
    accounts = _account_ids()
    # Seed an existing unreconciled internal transaction matching BRI row #3 (3,330,325 on 2026-01-09)
    with get_connection() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE username = 'finance'").fetchone()["id"]
        kat_id = conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"]
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, penerima_pengirim, keterangan, nominal_pokok,
                biaya_admin_kode_unik, total_mutasi, status_rekonsiliasi
            ) VALUES (?, 'Tim Finance', '2026-01-09', 'flip',
                '2026-01-09', '21:17:41', ?, 'KELUAR', ?, 'Flip Vendor',
                'Transfer Flip', 3330000, 325, 3330325, 'BELUM_REKON')
            """,
            (user_id, accounts["BRI"], kat_id),
        ).lastrowid
        conn.commit()

    pdf_bytes = BRI_PDF_PATH.read_bytes()
    prev = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": (BRI_PDF_PATH.name, pdf_bytes, "application/pdf")},
    )
    assert prev.status_code == 200
    assert vision_calls == []
    body = prev.json()
    assert body["rekening"]["kode_akun"] == "BRI"
    assert body["metode_ekstraksi"] == "Deterministik (Teks PDF)"
    assert len(body["rows"]) == 14
    assert body["summary"]["saldo_awal_periode"] == 214531779.0
    assert body["summary"]["total_cr"] == 178309.0
    assert body["summary"]["total_db"] == 22066136.0
    assert body["summary"]["saldo_akhir_periode"] == 192643952.0
    assert body["summary"]["selisih_saldo"] == 0.0
    assert body["summary"]["balance_valid"] is True

    saved = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": body["rekening"]["id"],
            "nama_file": body["nama_file"],
            "file_hash": body["file_hash"],
            "metode_ekstraksi": body["metode_ekstraksi"],
            "rows": [
                {
                    "tanggal": r["tanggal"],
                    "waktu": r["waktu"],
                    "uraian": r["uraian"],
                    "tipe": r["tipe"],
                    "nominal": r["nominal"],
                    "saldo": r["saldo"],
                }
                for r in body["rows"]
            ],
            "replace_existing": False,
        },
    )
    assert saved.status_code == 200
    save_data = saved.json()
    assert save_data["inserted_count"] == 14
    assert save_data["skipped_duplicates"] == 0
    assert save_data["reconciliation"]["matched_transactions"] == 1

    with get_connection() as conn:
        tx_row = conn.execute(
            "SELECT status_rekonsiliasi FROM transaksi_internal WHERE id = ?",
            (tx_id,),
        ).fetchone()
        tax_row = conn.execute(
            "SELECT status_rekonsiliasi, penyebab_selisih FROM mutasi_bank WHERE uraian = 'Tax'"
        ).fetchone()
    assert tx_row["status_rekonsiliasi"] == "SESUAI"
    assert tax_row["status_rekonsiliasi"] == "BELUM_TERCATAT"
    assert "Bunga / Pajak Bank" in tax_row["penyebab_selisih"]

    # Deleting batch must cascade mutasi & recalculate transaksi_internal back to BELUM_REKON
    deleted = client.delete(f"/api/v1/mutasi/batches/{save_data['batch_id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["recalculated_transactions"] == 1
    with get_connection() as conn:
        tx_after = conn.execute(
            "SELECT status_rekonsiliasi FROM transaksi_internal WHERE id = ?",
            (tx_id,),
        ).fetchone()
        assert conn.execute("SELECT COUNT(*) FROM mutasi_bank").fetchone()[0] == 0
    assert tx_after["status_rekonsiliasi"] == "BELUM_REKON"


def test_vector_pdf_uses_vision_per_page_and_detects_balance_mismatch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    page_responses = [
        {
            "no_rekening": "1783680837",
            "saldo_awal": 2180712,
            "saldo_akhir": None,
            "transaksi": [
                {
                    "tanggal": "2026-01-01",
                    "waktu": "16:28:32 WIB",
                    "uraian": "Transfer | BNI - PT FLIPTECH",
                    "tipe": "DB",
                    "nominal": 800353,
                    "saldo": 1380359,
                }
            ],
        },
        {
            "no_rekening": "1783680837",
            "saldo_awal": None,
            "saldo_akhir": 1000000,
            "transaksi": [
                {
                    "tanggal": "2026-01-01",
                    "waktu": "18:00:00 WIB",
                    "uraian": "Transfer Masuk",
                    "tipe": "CR",
                    "nominal": 210000,
                    "saldo": 1000000,  # Intentional mismatch (1380359 + 210000 != 1000000)
                }
            ],
        },
    ]

    async def fake_vision(**kwargs: Any) -> str:
        idx = len(calls)
        calls.append(kwargs)
        return json.dumps(page_responses[idx])

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fake_vision)
    headers = _login(client, "management", "management123")

    res = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("bni_wondr.pdf", _make_vector_like_pdf(2), "application/pdf")},
    )
    assert res.status_code == 200
    assert len(calls) == 2
    assert calls[0]["images"][0].content_type == "image/png"
    body = res.json()
    assert body["rekening"]["kode_akun"] == "BNI"
    assert body["rows"][0]["waktu"] == "16:28:32"
    assert body["summary"]["balance_valid"] is False
    assert any("PERINGATAN KERAS" in w for w in body["warnings"])


def test_duplicate_file_hash_and_overlapping_row_dedup_signature(client: TestClient) -> None:
    headers = _login(client, "finance", "finance123")
    pdf_bytes = BRI_PDF_PATH.read_bytes()

    prev = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("bri_part1.pdf", pdf_bytes, "application/pdf")},
    ).json()

    # Save first 10 rows as Batch 1
    first_save = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": prev["rekening"]["id"],
            "nama_file": "bri_part1.pdf",
            "file_hash": prev["file_hash"],
            "metode_ekstraksi": prev["metode_ekstraksi"],
            "rows": prev["rows"][:10],
            "replace_existing": False,
        },
    )
    assert first_save.status_code == 200
    assert first_save.json()["inserted_count"] == 10

    # Re-uploading exact same file_hash is warned in preview & rejected with 409 on save
    prev_dup = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("bri_part1_copy.pdf", pdf_bytes, "application/pdf")},
    )
    assert prev_dup.status_code == 200
    assert prev_dup.json()["duplicate_batch"]["id"] == first_save.json()["batch_id"]

    blocked = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": prev["rekening"]["id"],
            "nama_file": "bri_part1_copy.pdf",
            "file_hash": prev["file_hash"],
            "metode_ekstraksi": prev["metode_ekstraksi"],
            "rows": prev["rows"][:10],
            "replace_existing": False,
        },
    )
    assert blocked.status_code == 409

    # Overlapping PDF (rows 5..14, different file_hash) skips rows 5..9 via dedup_signature
    overlap_save = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": prev["rekening"]["id"],
            "nama_file": "bri_part2_overlap.pdf",
            "file_hash": "b" * 64,
            "metode_ekstraksi": prev["metode_ekstraksi"],
            "rows": prev["rows"][5:],
            "replace_existing": False,
        },
    )
    assert overlap_save.status_code == 200
    assert overlap_save.json()["inserted_count"] == 4
    assert overlap_save.json()["skipped_duplicates"] == 5

    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mutasi_bank").fetchone()[0] == 14


def test_printed_balance_mismatch_and_period_filter_and_jago_secondary_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_vision(**_kwargs: Any) -> str:
        return json.dumps(
            {
                "no_rekening": "500812786602",
                "saldo_awal": 5000000,  # Differs from row-derived opening (1,000,000) -> missing first row
                "saldo_akhir": 800000,
                "transaksi": [
                    {
                        "tanggal": "2026-01-05",
                        "waktu": "10:00:00",
                        "uraian": "Meta Ads",
                        "tipe": "DB",
                        "nominal": 200000,
                        "saldo": 800000,
                    }
                ],
            }
        )

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fake_vision)
    headers = _login(client, "finance", "finance123")

    prev = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("jago.pdf", _make_vector_like_pdf(1), "application/pdf")},
    )
    assert prev.status_code == 200
    body = prev.json()
    assert body["rekening"]["kode_akun"] == "Bank Jago"
    assert body["summary"]["printed_saldo_awal"] == 5000000.0
    assert body["summary"]["balance_valid"] is False
    assert any("Saldo awal turunan baris pertama tidak cocok" in w for w in body["warnings"])

    saved = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": body["rekening"]["id"],
            "no_rekening": body["detected_no_rekening"],
            "nama_file": "jago.pdf",
            "file_hash": body["file_hash"],
            "metode_ekstraksi": body["metode_ekstraksi"],
            "rows": [
                {
                    "tanggal": "2026-01-05",
                    "waktu": "10:00:00",
                    "uraian": "Meta Ads",
                    "tipe": "DB",
                    "nominal": 200000,
                    "saldo": 800000,
                },
                {
                    "tanggal": "2026-01-20",
                    "waktu": "12:00:00",
                    "uraian": "Topup Jago",
                    "tipe": "CR",
                    "nominal": 300000,
                    "saldo": 1100000,
                },
            ],
            "replace_existing": False,
        },
    )
    assert saved.status_code == 200

    filtered = client.get(
        "/api/v1/mutasi/rows",
        headers=headers,
        params={"tanggal_mulai": "2026-01-10", "tanggal_selesai": "2026-01-31"},
    )
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert len(items) == 1
    assert items[0]["uraian"] == "Topup Jago"
    assert items[0]["no_rekening"] == "500812786602"


def test_real_bni_vector_pdf_routes_to_vision_per_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    async def fake_vision(**kwargs: Any) -> str:
        calls.append(kwargs)
        if len(calls) == 1:
            return json.dumps(
                {
                    "no_rekening": "1783680837",
                    "saldo_awal": 2180712,
                    "saldo_akhir": None,
                    "transaksi": [
                        {
                            "tanggal": "2026-01-01",
                            "waktu": "16:28:32 WIB",
                            "uraian": "Transfer | BNI - PT FLIPTECH",
                            "tipe": "DB",
                            "nominal": 800353,
                            "saldo": 1380359,
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "no_rekening": "1783680837",
                "saldo_awal": None,
                "saldo_akhir": 1380359 if len(calls) == 7 else None,
                "transaksi": [],
            }
        )

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fake_vision)
    headers = _login(client, "finance", "finance123")
    res = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": (BNI_PDF_PATH.name, BNI_PDF_PATH.read_bytes(), "application/pdf")},
    )
    assert res.status_code == 200
    assert len(calls) == 7
    body = res.json()
    assert body["rekening"]["kode_akun"] == "BNI"
    assert body["summary"]["balance_valid"] is True
    assert len(body["rows"]) == 1

    # Replace mode overwrites Batch 1 cleanly
    replaced = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": prev["rekening"]["id"],
            "nama_file": "bri_replaced.pdf",
            "file_hash": prev["file_hash"],
            "metode_ekstraksi": prev["metode_ekstraksi"],
            "rows": prev["rows"],
            "replace_existing": True,
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["inserted_count"] == 10
    assert replaced.json()["skipped_duplicates"] == 4
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mutasi_bank").fetchone()[0] == 14


def test_printed_balance_mismatch_and_period_filter_and_jago_secondary_account(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_vision(**_kwargs: Any) -> str:
        return json.dumps(
            {
                "no_rekening": "500812786602",
                "saldo_awal": 5000000,  # Differs from row-derived opening (1,000,000) -> missing first row
                "saldo_akhir": 800000,
                "transaksi": [
                    {
                        "tanggal": "2026-01-05",
                        "waktu": "10:00:00",
                        "uraian": "Meta Ads",
                        "tipe": "DB",
                        "nominal": 200000,
                        "saldo": 800000,
                    }
                ],
            }
        )

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fake_vision)
    headers = _login(client, "finance", "finance123")

    prev = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("jago.pdf", _make_vector_like_pdf(1), "application/pdf")},
    )
    assert prev.status_code == 200
    body = prev.json()
    assert body["rekening"]["kode_akun"] == "Bank Jago"
    assert body["summary"]["printed_saldo_awal"] == 5000000.0
    assert body["summary"]["balance_valid"] is False
    assert any("Saldo awal turunan baris pertama tidak cocok" in w for w in body["warnings"])

    saved = client.post(
        "/api/v1/mutasi/save",
        headers=headers,
        json={
            "rekening_id": body["rekening"]["id"],
            "no_rekening": body["detected_no_rekening"],
            "nama_file": "jago.pdf",
            "file_hash": body["file_hash"],
            "metode_ekstraksi": body["metode_ekstraksi"],
            "rows": [
                {
                    "tanggal": "2026-01-05",
                    "waktu": "10:00:00",
                    "uraian": "Meta Ads",
                    "tipe": "DB",
                    "nominal": 200000,
                    "saldo": 800000,
                },
                {
                    "tanggal": "2026-01-20",
                    "waktu": "12:00:00",
                    "uraian": "Topup Jago",
                    "tipe": "CR",
                    "nominal": 300000,
                    "saldo": 1100000,
                },
            ],
            "replace_existing": False,
        },
    )
    assert saved.status_code == 200

    filtered = client.get(
        "/api/v1/mutasi/rows",
        headers=headers,
        params={"tanggal_mulai": "2026-01-10", "tanggal_selesai": "2026-01-31"},
    )
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert len(items) == 1
    assert items[0]["uraian"] == "Topup Jago"
    assert items[0]["no_rekening"] == "500812786602"


def test_real_bni_vector_pdf_routes_to_vision_per_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    async def fake_vision(**kwargs: Any) -> str:
        calls.append(kwargs)
        if len(calls) == 1:
            return json.dumps(
                {
                    "no_rekening": "1783680837",
                    "saldo_awal": 2180712,
                    "saldo_akhir": None,
                    "transaksi": [
                        {
                            "tanggal": "2026-01-01",
                            "waktu": "16:28:32 WIB",
                            "uraian": "Transfer | BNI - PT FLIPTECH",
                            "tipe": "DB",
                            "nominal": 800353,
                            "saldo": 1380359,
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "no_rekening": "1783680837",
                "saldo_awal": None,
                "saldo_akhir": 1380359 if len(calls) == 7 else None,
                "transaksi": [],
            }
        )

    monkeypatch.setattr(mutasi_parser_module, "complete_vision", fake_vision)
    headers = _login(client, "finance", "finance123")
    res = client.post(
        "/api/v1/mutasi/preview",
        headers=headers,
        data={"rekening_id": "AUTO"},
        files={"file": (BNI_PDF_PATH.name, BNI_PDF_PATH.read_bytes(), "application/pdf")},
    )
    assert res.status_code == 200
    assert len(calls) == 7
    body = res.json()
    assert body["rekening"]["kode_akun"] == "BNI"
    assert body["summary"]["balance_valid"] is True
    assert len(body["rows"]) == 1
