from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fitz
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import init_db
from app.main import app
from app.services import ai_service as ai_service_module
from app.services import vision as vision_service


@pytest.fixture(autouse=True)
def isolated_ai_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_db = tmp_path / "ai_test.db"
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(settings, "database_path", str(test_db))
    monkeypatch.setattr(settings, "storage_dir", str(storage_dir))
    monkeypatch.setattr(settings, "vision_model", "gemini/gemini-3.5-flash-lite")
    init_db()


client = TestClient(app)


def _login(username: str, password: str) -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _make_vector_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for idx in range(pages):
        page = doc.new_page()
        page.insert_text((40, 40), f"MUTASI REKENING HALAMAN {idx + 1}")
    raw = doc.tobytes()
    doc.close()
    return raw


def _golden_vision_payload(case_id: str) -> dict[str, Any]:
    """Return exact ground-truth JSON matching GoldenEvalCase expectations."""
    if case_id == "normal_qris_keluar":
        return {
            "tanggal_transaksi": "2026-01-06",
            "waktu_transaksi": "18:43:38",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Biaya-Operasional",
            "penerima_pengirim": "Griya Kardus Klaten",
            "keterangan": "QRIS Griya Kardus",
            "nominal_pokok": 70000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 70000,
            "jenis_struk": "qris_receipt",
            "slot_a": [
                {
                    "filename": "photo_2026-01-07_08-28-34.jpg",
                    "document_type": "qris_receipt",
                    "amount": 70000,
                    "date": "2026-01-06",
                    "time": "18:43:38",
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
        }
    if case_id == "flip_keluar":
        return {
            "tanggal_transaksi": "2026-01-01",
            "waktu_transaksi": "16:28:32",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Bahan Baku",
            "penerima_pengirim": "Eling Muhammad Falah",
            "keterangan": "Tepung beras",
            "nominal_pokok": 800000,
            "biaya_admin_kode_unik": 353,
            "total_mutasi": 800353,
            "jenis_struk": "flip_bank_to_fliptech",
            "slot_a": [
                {
                    "filename": "photo_2026-01-01_16-28-57.jpg",
                    "document_type": "flip_bank_to_fliptech",
                    "amount": 800353,
                    "date": "2026-01-01",
                    "time": "16:28:32",
                    "sender_digits": "1783680837",
                    "recipient_digits": "1211146477",
                    "company_account": "BNI",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_b": [
                {
                    "filename": "photo_2026-01-01_16-29-59.jpg",
                    "document_type": "flip_to_recipient",
                    "amount": 800000,
                    "date": "2026-01-01",
                    "time": "16:29:59",
                    "sender_digits": None,
                    "recipient_digits": "004801016512532",
                    "company_account": None,
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_c": [],
            "notes": "",
        }
    if case_id == "flip_pindah_buku":
        return {
            "tanggal_transaksi": "2026-01-17",
            "waktu_transaksi": "10:32:51",
            "rekening": "BNI",
            "rekening_tujuan": "BRI Operasional",
            "tipe": "PINDAH_BUKU",
            "kategori": "Transfer Antar Rekening (Pindah Buku)",
            "penerima_pengirim": "Ilham Nawan Rasyid",
            "keterangan": "Iuran Kelas Keuangan",
            "nominal_pokok": 74500,
            "biaya_admin_kode_unik": 325,
            "total_mutasi": 74825,
            "jenis_struk": "flip_bank_to_fliptech",
            "slot_a": [
                {
                    "filename": "photo_2026-01-17_10-33-45.jpg",
                    "document_type": "flip_bank_to_fliptech",
                    "amount": 74825,
                    "date": "2026-01-17",
                    "time": "10:32:51",
                    "sender_digits": "1783680837",
                    "recipient_digits": None,
                    "company_account": "BNI",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_b": [
                {
                    "filename": "photo_2026-01-17_10-34-19.jpg",
                    "document_type": "flip_to_recipient",
                    "amount": 74500,
                    "date": "2026-01-17",
                    "time": "10:33:10",
                    "sender_digits": None,
                    "recipient_digits": "174601000418533",
                    "company_account": "BRI Operasional",
                    "sender_excluded": False,
                    "is_unpaid": False,
                }
            ],
            "slot_c": [],
            "notes": "",
        }
    return {
        "tanggal_transaksi": "2026-01-17",
        "waktu_transaksi": "10:40:46",
        "rekening": "BNI",
        "rekening_tujuan": None,
        "tipe": "KELUAR",
        "kategori": "Biaya-Perlengkapan Kantor dan Administrasi",
        "penerima_pengirim": "Muhamad Ali Shodiqi",
        "keterangan": "Plakat Workshop",
        "nominal_pokok": 75000,
        "biaya_admin_kode_unik": 0,
        "total_mutasi": 75000,
        "jenis_struk": "bank_transfer",
        "slot_a": [
            {
                "filename": "photo_2026-01-17_10-37-42.jpg",
                "document_type": "qris_receipt",
                "amount": 75000,
                "date": "2026-01-17",
                "time": "10:37:42",
                "sender_digits": "0568158096",
                "recipient_digits": None,
                "company_account": None,
                "sender_excluded": True,
                "is_unpaid": False,
            }
        ],
        "slot_b": [
            {
                "filename": "photo_2026-01-17_10-41-34.jpg",
                "document_type": "bank_transfer",
                "amount": 75000,
                "date": "2026-01-17",
                "time": "10:40:46",
                "sender_digits": "1783680837",
                "recipient_digits": "0568158096",
                "company_account": "BNI",
                "sender_excluded": False,
                "is_unpaid": False,
            }
        ],
        "slot_c": [],
        "notes": "",
    }


def test_only_management_can_access_ai_governance_and_switch_model() -> None:
    staff_headers = _login("staff", "staff123")
    finance_headers = _login("finance", "finance123")
    mgmt_headers = _login("management", "management123")

    for hdr in (staff_headers, finance_headers):
        assert client.get("/api/v1/ai/overview", headers=hdr).status_code == 403
        assert (
            client.put("/api/v1/ai/model", headers=hdr, json={"model": "gemini/gemini-3.8-flash"}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/ai/evaluate",
                headers=hdr,
                json={"candidate_model": "gemini/gemini-3.8-flash"},
            ).status_code
            == 403
        )

    ov = client.get("/api/v1/ai/overview", headers=mgmt_headers)
    assert ov.status_code == 200
    ov_body = ov.json()
    assert ov_body["active_model"]["id"] == "gemini/gemini-3.5-flash-lite"
    assert all(item["id"].startswith("gemini/") for item in ov_body["catalog"])

    switched = client.put(
        "/api/v1/ai/model",
        headers=mgmt_headers,
        json={"model": "gemini/gemini-3.8-flash", "usd_to_idr_rate": 16500},
    )
    assert switched.status_code == 200
    assert switched.json()["active_model"]["id"] == "gemini/gemini-3.8-flash"
    assert switched.json()["usd_to_idr_rate"] == 16500
    assert ai_service_module.get_active_vision_model() == "gemini/gemini-3.8-flash"


def test_struk_and_mutasi_track_token_usage_cost_and_respect_switched_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgmt_headers = _login("management", "management123")
    finance_headers = _login("finance", "finance123")

    # Switch model via Management
    assert (
        client.put(
            "/api/v1/ai/model",
            headers=mgmt_headers,
            json={"model": "gemini/gemini-3.8-flash", "usd_to_idr_rate": 16000},
        ).status_code
        == 200
    )

    called_models: list[str] = []

    async def fake_acompletion(**kwargs: Any):
        called_models.append(kwargs["model"])
        user_text = kwargs["messages"][1]["content"][0]["text"]
        if "HAL-" in user_text:
            body = {
                "bank": "BNI",
                "no_rekening": "1783680837",
                "saldo_awal": 1000000,
                "saldo_akhir": 1200000,
                "transaksi": [
                    {
                        "tanggal": "2026-01-05",
                        "waktu": "10:00:00",
                        "uraian": "Transfer Masuk",
                        "tipe": "CR",
                        "nominal": 200000,
                        "saldo": 1200000,
                    }
                ],
            }
        else:
            body = _golden_vision_payload("normal_qris_keluar")
            body["slot_a"][0]["filename"] = "struk.jpg"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
            _hidden_params={"response_cost": 0.00155},
        )

    monkeypatch.setattr(vision_service.litellm, "acompletion", fake_acompletion)

    # 1) Input Struk extract + save
    ext_res = client.post(
        "/api/v1/struk/extract",
        headers=finance_headers,
        data={"tab_type": "normal", "is_cash": "false"},
        files=[("slot_a", ("struk.jpg", b"\xff\xd8\xff\xe0dummy", "image/jpeg"))],
    )
    assert ext_res.status_code == 200
    ext_body = ext_res.json()
    assert called_models[-1] == "gemini/gemini-3.8-flash"
    assert ext_body["ai_usage"]["used_ai"] is True
    assert ext_body["ai_usage"]["total_tokens"] == 1500
    assert ext_body["ai_usage"]["cost_usd"] == pytest.approx(0.00155)
    assert ext_body["ai_usage"]["cost_idr"] == pytest.approx(24.8)

    meta = client.get("/api/v1/struk/metadata", headers=finance_headers).json()
    bni_id = next(r["id"] for r in meta["rekening_perusahaan"] if r["kode_akun"] == "BNI")
    kat_id = next(c["id"] for c in meta["kategori_sop"] if c["nama_kategori"] == "Biaya-Operasional")

    save_res = client.post(
        "/api/v1/struk/save",
        headers=finance_headers,
        json={
            "staging_id": ext_body["staging_id"],
            "tanggal_transaksi": "2026-01-06",
            "waktu_transaksi": "18:43:38",
            "rekening_sumber_id": bni_id,
            "rekening_tujuan_id": None,
            "tipe": "KELUAR",
            "kategori_id": kat_id,
            "penerima_pengirim": "Griya Kardus",
            "keterangan": "QRIS",
            "nominal_pokok": 70000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 70000,
        },
    )
    assert save_res.status_code == 200
    assert save_res.json()["ai_usage"]["total_tokens"] == 1500

    recent_res = client.get("/api/v1/struk/recent?limit=10", headers=finance_headers)
    assert recent_res.status_code == 200
    recent_body = recent_res.json()
    assert recent_body["items"][0]["ai_usage"]["total_tokens"] == 1500
    assert recent_body["ai_cost_summary"]["total_tokens"] == 1500
    assert recent_body["ai_cost_summary"]["total_cost_idr"] == pytest.approx(24.8)

    # 2) Input Mutasi preview (2 pages via Vision AI) + save
    prev_res = client.post(
        "/api/v1/mutasi/preview",
        headers=finance_headers,
        data={"rekening_id": "AUTO"},
        files={"file": ("bni_scan.pdf", _make_vector_pdf(2), "application/pdf")},
    )
    assert prev_res.status_code == 200
    prev_body = prev_res.json()
    assert called_models[-1] == "gemini/gemini-3.8-flash"
    assert prev_body["ai_usage"]["pages_processed"] == 2
    assert prev_body["ai_usage"]["total_tokens"] == 3000
    assert prev_body["ai_usage"]["cost_usd"] == pytest.approx(0.0031)
    assert prev_body["ai_usage"]["cost_idr"] == pytest.approx(49.6)

    save_mut_res = client.post(
        "/api/v1/mutasi/save",
        headers=finance_headers,
        json={
            "rekening_id": prev_body["rekening"]["id"],
            "no_rekening": prev_body["detected_no_rekening"],
            "nama_file": prev_body["nama_file"],
            "file_hash": prev_body["file_hash"],
            "metode_ekstraksi": prev_body["metode_ekstraksi"],
            "rows": prev_body["rows"],
            "ai_usage": prev_body["ai_usage"],
        },
    )
    assert save_mut_res.status_code == 200
    batches_res = client.get("/api/v1/mutasi/batches", headers=finance_headers).json()
    assert batches_res["items"][0]["ai_usage"]["total_tokens"] == 3000
    assert batches_res["ai_cost_summary"]["total_cost_idr"] == pytest.approx(49.6)

    # 3) Overview aggregates both features
    ov = client.get("/api/v1/ai/overview", headers=mgmt_headers).json()
    assert ov["usage_summary"]["total_tokens"] == 4500
    assert ov["usage_summary"]["by_feature"]["input_struk"]["total_tokens"] == 1500
    assert ov["usage_summary"]["by_feature"]["input_mutasi"]["total_tokens"] == 3000


def test_ai_evaluation_pass_and_regression_fail_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    mgmt_headers = _login("management", "management123")

    def _case_from_messages(messages: list[dict[str, Any]]) -> str:
        text = " ".join(
            part["text"] for part in messages[1]["content"] if part.get("type") == "text"
        )
        if "08-28-34" in text:
            return "normal_qris_keluar"
        if "16-28-57" in text:
            return "flip_keluar"
        if "10-33-45" in text:
            return "flip_pindah_buku"
        return "reimburse_keluar"

    async def fake_acompletion(**kwargs: Any):
        case_id = _case_from_messages(kwargs["messages"])
        model = kwargs["model"]
        payload = _golden_vision_payload(case_id)
        # Candidate "bad/model" introduces a critical regression on flip_keluar
        if model == "bad/regression-model" and case_id == "flip_keluar":
            payload["total_mutasi"] = 999999
            payload["slot_a"][0]["amount"] = 999999
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=800, completion_tokens=200, total_tokens=1000),
            _hidden_params={"response_cost": 0.0005},
        )

    monkeypatch.setattr(vision_service.litellm, "acompletion", fake_acompletion)

    pass_res = client.post(
        "/api/v1/ai/evaluate",
        headers=mgmt_headers,
        json={
            "candidate_model": "gemini/gemini-3.8-flash",
            "sample_size": 4,
            "compare_baseline": True,
        },
    )
    assert pass_res.status_code == 200
    pass_body = pass_res.json()
    assert pass_body["gate_decision"] == "PASS"
    assert pass_body["summary"]["schema_validity_pct"] == 100.0
    assert pass_body["summary"]["critical_pass_pct"] == 100.0
    assert pass_body["summary"]["comparison"]["regressions"] == []

    fail_res = client.post(
        "/api/v1/ai/evaluate",
        headers=mgmt_headers,
        json={
            "candidate_model": "bad/regression-model",
            "sample_size": 4,
            "compare_baseline": True,
        },
    )
    assert fail_res.status_code == 200
    fail_body = fail_res.json()
    assert fail_body["gate_decision"] == "FAIL"
    assert "flip_keluar" in fail_body["summary"]["comparison"]["regressions"]

    hist = client.get("/api/v1/ai/evaluations", headers=mgmt_headers)
    assert hist.status_code == 200
    assert len(hist.json()["items"]) == 2
