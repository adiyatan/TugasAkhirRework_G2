import hashlib
import json
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
    monkeypatch.setattr(settings, "vision_model", "gemini/gemini-2.5-flash")
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def vision(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "response": None, "error": None}

    async def fake_complete_vision(**kwargs: Any) -> str:
        state["calls"].append(kwargs)
        if state["error"] is not None:
            raise state["error"]
        response = state["response"]
        if isinstance(response, str):
            return response
        return json.dumps(response)

    monkeypatch.setattr(struk_service_module, "complete_vision", fake_complete_vision)
    return state


def _login(client: TestClient, username: str = "staff", password: str = "staff123") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _slot_file(
    *,
    slot: str,
    filename: str,
    amount: int | None,
    document_type: str = "bank_transfer",
    date: str | None = "2026-01-09",
    time: str | None = "14:10:00",
    sender_digits: str | None = "1783680837",
    recipient_digits: str | None = None,
    company_account: str | None = "BNI",
    sender_excluded: bool = False,
    is_unpaid: bool = False,
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
        "sender_excluded": sender_excluded,
        "is_unpaid": is_unpaid,
    }


def _payload(
    *,
    tab_type: str = "normal",
    slot_a: list[dict[str, Any]],
    slot_b: list[dict[str, Any]] | None = None,
    slot_c: list[dict[str, Any]] | None = None,
    total_mutasi: int,
    nominal_pokok: int | None = None,
    biaya_admin_kode_unik: int | None = None,
    tipe: str = "KELUAR",
    kategori: str = "Bahan Baku",
    rekening: str = "BNI",
    rekening_tujuan: str | None = None,
    tanggal_transaksi: str = "2026-01-09",
    waktu_transaksi: str = "14:10:00",
    penerima_pengirim: str = "Toko Contoh",
    keterangan: str = "Pembelian bahan baku",
    jenis_struk: str = "bank_transfer",
) -> dict[str, Any]:
    nominal = total_mutasi if nominal_pokok is None else nominal_pokok
    return {
        "tanggal_transaksi": tanggal_transaksi,
        "waktu_transaksi": waktu_transaksi,
        "rekening": rekening,
        "rekening_tujuan": rekening_tujuan,
        "tipe": tipe,
        "kategori": kategori,
        "penerima_pengirim": penerima_pengirim,
        "keterangan": keterangan,
        "nominal_pokok": nominal,
        "biaya_admin_kode_unik": total_mutasi - nominal if biaya_admin_kode_unik is None else biaya_admin_kode_unik,
        "total_mutasi": total_mutasi,
        "jenis_struk": jenis_struk,
        "slot_a": slot_a,
        "slot_b": slot_b or [],
        "slot_c": slot_c or [],
        "notes": "",
    }


def _post(
    client: TestClient,
    headers: dict[str, str],
    *,
    tab_type: str,
    slot_a: list[tuple[str, bytes]] | None = None,
    slot_b: list[tuple[str, bytes]] | None = None,
    slot_c: list[tuple[str, bytes]] | None = None,
    is_cash: bool = False,
):
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for slot, values in (("slot_a", slot_a or []), ("slot_b", slot_b or []), ("slot_c", slot_c or [])):
        for filename, data in values:
            files.append((slot, (filename, data, "image/jpeg")))
    return client.post(
        "/api/v1/struk/extract",
        headers=headers,
        data={"tab_type": tab_type, "is_cash": str(is_cash).lower()},
        files=files,
    )


def _image(label: str) -> bytes:
    return f"image-{label}".encode("utf-8")


def test_extract_requires_authentication(client: TestClient, vision: dict[str, Any]) -> None:
    response = _post(client, {}, tab_type="normal", slot_a=[("a.jpg", _image("a"))])

    assert response.status_code == 401
    assert vision["calls"] == []


def test_extract_validates_slot_requirements(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)

    no_a = _post(client, headers, tab_type="normal", slot_b=[("b.jpg", _image("b"))])
    assert no_a.status_code in {400, 422}

    two_a = _post(
        client,
        headers,
        tab_type="flip",
        slot_a=[("a1.jpg", _image("a1")), ("a2.jpg", _image("a2"))],
        slot_b=[("b.jpg", _image("b"))],
    )
    assert two_a.status_code in {400, 422}

    no_b = _post(client, headers, tab_type="flip", slot_a=[("a.jpg", _image("a"))])
    assert no_b.status_code in {400, 422}
    assert vision["calls"] == []


def test_extract_normal_with_only_slot_a_is_accepted(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        tab_type="normal",
        slot_a=[_slot_file(slot="A", filename="a.jpg", amount=75000)],
        total_mutasi=75000,
        penerima_pengirim="TOKO CONTOH",
    )

    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])

    assert response.status_code == 200
    body = response.json()
    assert body["staging_id"]
    assert body["extracted"]["total_mutasi"] == 75000
    assert body["slots"]["A"][0]["filename"] == "a.jpg"
    assert body["errors"] == []
    assert len(vision["calls"]) == 1


def test_extract_flip_1a_3b_creates_one_staging_with_four_files(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        tab_type="flip",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=2700329,
                document_type="flip_bank_to_fliptech",
                recipient_digits="777",
            )
        ],
        slot_b=[
            _slot_file(
                slot="B",
                filename="b1.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                sender_digits=None,
                recipient_digits="096",
                company_account=None,
            ),
            _slot_file(
                slot="B",
                filename="b2.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                sender_digits=None,
                recipient_digits="777",
                company_account=None,
            ),
            _slot_file(
                slot="B",
                filename="b3.jpg",
                amount=900000,
                document_type="flip_to_recipient",
                sender_digits=None,
                recipient_digits=None,
                company_account=None,
            ),
        ],
        total_mutasi=2700329,
        nominal_pokok=2700000,
        jenis_struk="flip_bank_to_fliptech",
        penerima_pengirim="Muhamad Ali Shodiqi; Elin; Toko Sumber Rejeki",
    )

    response = _post(
        client,
        headers,
        tab_type="flip",
        slot_a=[("a.jpg", _image("a"))],
        slot_b=[("b1.jpg", _image("b1")), ("b2.jpg", _image("b2")), ("b3.jpg", _image("b3"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["extracted"]["total_mutasi"] == 2700329
    assert body["extracted"]["nominal_pokok"] == 2700000
    assert body["extracted"]["biaya_admin_kode_unik"] == 329
    assert [row["slot"] for row in body["manifest"]] == ["A", "B", "B", "B"]

    with get_connection() as conn:
        staging = conn.execute("SELECT * FROM upload_staging").fetchone()
        assert staging is not None
        manifest = json.loads(staging["manifest_json"])
        assert len(manifest) == 4
        assert [row["slot"] for row in manifest] == ["A", "B", "B", "B"]
        assert all(row["sha256"] for row in manifest)


def test_extract_rejects_duplicate_files_inside_batch(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)
    duplicate = _image("same")

    response = _post(
        client,
        headers,
        tab_type="normal",
        slot_a=[("a.jpg", duplicate)],
        slot_b=[("b.jpg", duplicate)],
    )

    assert response.status_code in {400, 409, 422}
    assert "duplikat" in response.text.lower()
    assert vision["calls"] == []


def test_extract_rejects_existing_file_hash_with_previous_transaction_reference(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    data = _image("existing")
    file_hash = hashlib.sha256(data).hexdigest()
    with get_connection() as conn:
        user_id = conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()["id"]
        bni_id = conn.execute("SELECT id FROM rekening_perusahaan WHERE kode_akun = 'BNI'").fetchone()["id"]
        kategori_id = conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO upload_staging (id, user_id, tab_type, is_cash, status, manifest_json, expires_at)
            VALUES ('stg_existing', ?, 'normal', 0, 'SAVED', '[]', '2099-01-01T00:00:00')
            """,
            (user_id,),
        )
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                staging_id, created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, total_mutasi
            ) VALUES ('stg_existing', ?, 'Tim Staff', '2026-01-09', 'normal',
                '2026-01-09', '14:10:00', ?, 'KELUAR', ?, 1000)
            """,
            (user_id, bni_id, kategori_id),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename, file_hash,
                jenis_struk, status_file
            ) VALUES (?, 'A', 'existing.jpg', 'existing.jpg', ?,
                'bank_transfer', 'TERPAKAI_UTAMA')
            """,
            (tx_id, file_hash),
        )
        conn.commit()

    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", data)])

    assert response.status_code in {400, 409, 422}
    assert str(tx_id) in response.text
    assert vision["calls"] == []


def test_extract_calls_vision_once_with_all_labeled_images_and_dynamic_prompt(
    client: TestClient, vision: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _login(client)
    monkeypatch.setattr(settings, "vision_api_key", "test-vision-key")
    vision["response"] = _payload(
        tab_type="flip",
        slot_a=[
            _slot_file(slot="A", filename="a.jpg", amount=2700329, document_type="flip_bank_to_fliptech")
        ],
        slot_b=[
            _slot_file(slot="B", filename="b1.jpg", amount=900000, document_type="flip_to_recipient", sender_digits=None),
            _slot_file(slot="B", filename="b2.jpg", amount=900000, document_type="flip_to_recipient", sender_digits=None),
            _slot_file(slot="B", filename="b3.jpg", amount=900000, document_type="flip_to_recipient", sender_digits=None),
        ],
        total_mutasi=2700329,
        nominal_pokok=2700000,
    )

    response = _post(
        client,
        headers,
        tab_type="flip",
        slot_a=[("a.jpg", _image("a"))],
        slot_b=[("b1.jpg", _image("b1")), ("b2.jpg", _image("b2")), ("b3.jpg", _image("b3"))],
    )

    assert response.status_code == 200
    assert len(vision["calls"]) == 1
    call = vision["calls"][0]
    assert call["model"] == "gemini/gemini-2.5-flash"
    assert call["api_key"] == "test-vision-key"
    assert "flip" in call["prompt"]
    assert "1783680837" in call["prompt"]
    assert "0568158096" in call["prompt"]
    assert "Bahan Baku" in call["prompt"]
    labels = [f"SLOT {image.slot} - {image.filename}" for image in call["images"]]
    assert labels == ["SLOT A - a.jpg", "SLOT B - b1.jpg", "SLOT B - b2.jpg", "SLOT B - b3.jpg"]


def test_extract_invalid_ai_json_returns_502_and_creates_no_staging(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["response"] = "not json"

    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])

    assert response.status_code == 502
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM upload_staging").fetchone()[0] == 0


def test_extract_vision_failure_returns_502_and_creates_no_staging(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["error"] = RuntimeError("provider authentication failed")

    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])

    assert response.status_code == 502
    assert "provider" in response.text.lower()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM upload_staging").fetchone()[0] == 0


def test_normal_tab_rule_violations_are_returned_as_blocking_errors(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    unpaid = _payload(
        tab_type="normal",
        slot_a=[_slot_file(slot="A", filename="a.jpg", amount=75000, is_unpaid=True)],
        total_mutasi=75000,
    )
    vision["response"] = unpaid
    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])
    assert response.status_code == 200
    assert any("belum bayar" in error.lower() for error in response.json()["errors"])

    flip = _payload(
        tab_type="normal",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=2700329,
                document_type="flip_bank_to_fliptech",
                recipient_digits="777",
            )
        ],
        total_mutasi=2700329,
    )
    vision["response"] = flip
    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])
    assert response.status_code == 200
    assert any("tab flip" in error.lower() for error in response.json()["errors"])

    excluded = _payload(
        tab_type="normal",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=75000,
                sender_digits="0568158096",
                sender_excluded=True,
            )
        ],
        total_mutasi=75000,
    )
    vision["response"] = excluded
    response = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("a"))])
    assert response.status_code == 200
    assert any("reimburse" in error.lower() for error in response.json()["errors"])


def test_flip_amount_rule_and_date_mismatch(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)
    mismatch = _payload(
        tab_type="flip",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=2700329,
                document_type="flip_bank_to_fliptech",
                date="2026-01-09",
            )
        ],
        slot_b=[
            _slot_file(
                slot="B",
                filename="b1.jpg",
                amount=2700000,
                document_type="flip_to_recipient",
                sender_digits=None,
                date="2026-01-10",
            )
        ],
        total_mutasi=2700329,
        nominal_pokok=2700000,
    )
    vision["response"] = mismatch
    response = _post(
        client,
        headers,
        tab_type="flip",
        slot_a=[("a.jpg", _image("a"))],
        slot_b=[("b1.jpg", _image("b1"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert any("tanggal" in warning.lower() for warning in body["warnings"])
    assert "total_mutasi" in body["locked_fields"]

    too_far = _payload(
        tab_type="flip",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=2750000,
                document_type="flip_bank_to_fliptech",
            )
        ],
        slot_b=[
            _slot_file(
                slot="B",
                filename="b1.jpg",
                amount=2700000,
                document_type="flip_to_recipient",
                sender_digits=None,
            )
        ],
        total_mutasi=2750000,
        nominal_pokok=2700000,
    )
    vision["response"] = too_far
    response = _post(
        client,
        headers,
        tab_type="flip",
        slot_a=[("a.jpg", _image("a"))],
        slot_b=[("b1.jpg", _image("b1"))],
    )
    assert response.status_code == 200
    assert any("1000" in error or "selisih" in error.lower() for error in response.json()["errors"])


def test_extract_rejects_slot_c_outside_flip(client: TestClient, vision: dict[str, Any]) -> None:
    headers = _login(client)
    for tab in ("normal", "slip_gaji", "reimburse"):
        slots: dict[str, Any] = {
            "slot_a": [("a.jpg", _image(f"a-{tab}"))],
            "slot_c": [("c.jpg", _image(f"c-{tab}"))],
        }
        if tab != "normal":
            slots["slot_b"] = [("b.jpg", _image(f"b-{tab}"))]
        resp = _post(client, headers, tab_type=tab, **slots)
        assert resp.status_code == 400
    assert vision["calls"] == []


def test_account_matching_avoids_short_middle_false_positive_and_splits_jago(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    # Recipient '100' appears in middle of BRI (306601000009566) but is not a suffix -> must NOT become PINDAH_BUKU
    vision["response"] = _payload(
        tab_type="normal",
        slot_a=[
            _slot_file(
                slot="A",
                filename="a.jpg",
                amount=50000,
                sender_digits="508090335901",
                recipient_digits="100",
                company_account="Bank Jago",
            )
        ],
        total_mutasi=50000,
        rekening="Bank Jago",
    )
    resp = _post(client, headers, tab_type="normal", slot_a=[("a.jpg", _image("jago"))])
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["extracted"]["rekening"] == "Bank Jago"
    assert body["extracted"]["tipe"] == "KELUAR"
    assert body["extracted"]["rekening_tujuan_id"] is None


def test_reimburse_allows_small_negative_diff_and_blocks_excluded_slot_b(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        tab_type="reimburse",
        slot_a=[_slot_file(slot="A", filename="nota.jpg", amount=75500, sender_digits="096", company_account=None)],
        slot_b=[_slot_file(slot="B", filename="pt.jpg", amount=75000, sender_digits="1783680837", company_account="BNI")],
        total_mutasi=75000,
        nominal_pokok=75500,
        biaya_admin_kode_unik=0,
    )
    resp = _post(
        client,
        headers,
        tab_type="reimburse",
        slot_a=[("nota.jpg", _image("nota"))],
        slot_b=[("pt.jpg", _image("pt"))],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["extracted"]["total_mutasi"] == 75000
    assert body["extracted"]["nominal_pokok"] == 75000
    assert body["extracted"]["biaya_admin_kode_unik"] == 0
    assert any("toleransi" in w.lower() for w in body["warnings"])

    # Excluded sender in Slot B must be blocked
    vision["response"] = _payload(
        tab_type="reimburse",
        slot_a=[_slot_file(slot="A", filename="nota.jpg", amount=75000, sender_digits="096", company_account=None)],
        slot_b=[_slot_file(slot="B", filename="pt2.jpg", amount=75000, sender_digits="0568158096", sender_excluded=True, company_account=None)],
        total_mutasi=75000,
    )
    blocked = _post(
        client,
        headers,
        tab_type="reimburse",
        slot_a=[("nota.jpg", _image("nota2"))],
        slot_b=[("pt2.jpg", _image("pt2"))],
    )
    assert blocked.status_code == 200
    assert any("dikecualikan" in e.lower() for e in blocked.json()["errors"])


def test_slip_gaji_sums_multiple_direct_transfers_in_slot_b(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)
    vision["response"] = _payload(
        tab_type="slip_gaji",
        slot_a=[_slot_file(slot="A", filename="slip.jpg", amount=2000000, document_type="slip_gaji", company_account=None)],
        slot_b=[
            _slot_file(slot="B", filename="b1.jpg", amount=1200000, document_type="bank_transfer", sender_digits="1783680837", company_account="BNI"),
            _slot_file(slot="B", filename="b2.jpg", amount=800000, document_type="bank_transfer", sender_digits="1783680837", company_account="BNI"),
        ],
        total_mutasi=2000000,
        kategori="Biaya-Gaji Karyawan",
    )
    resp = _post(
        client,
        headers,
        tab_type="slip_gaji",
        slot_a=[("slip.jpg", _image("slip-multi"))],
        slot_b=[("b1.jpg", _image("b1-multi")), ("b2.jpg", _image("b2-multi"))],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["extracted"]["total_mutasi"] == 2000000
    assert body["extracted"]["nominal_pokok"] == 2000000


def test_normal_tab_allows_incoming_flip_recipient_and_excluded_sender_and_reimburse_handles_flip_pair(
    client: TestClient, vision: dict[str, Any]
) -> None:
    headers = _login(client)

    # 1. Incoming MASUK via Flip recipient receipt on normal tab
    vision["response"] = _payload(
        tab_type="normal",
        tipe="MASUK",
        kategori="Pendapatan Usaha (Penjualan Lainnya)",
        slot_a=[
            _slot_file(
                slot="A",
                filename="in_flip.jpg",
                amount=15000,
                document_type="flip_to_recipient",
                sender_digits=None,
                recipient_digits="1783680837",
                company_account="BNI",
            )
        ],
        total_mutasi=15000,
    )
    res_flip_in = _post(client, headers, tab_type="normal", slot_a=[("in_flip.jpg", _image("in_flip"))])
    assert res_flip_in.status_code == 200
    assert res_flip_in.json()["errors"] == []

    # 2. Incoming MASUK from excluded personal account on normal tab
    vision["response"] = _payload(
        tab_type="normal",
        tipe="MASUK",
        kategori="Pendapatan Usaha (Penjualan Lainnya)",
        slot_a=[
            _slot_file(
                slot="A",
                filename="in_excl.jpg",
                amount=195000,
                sender_digits="096",
                recipient_digits="1783680837",
                company_account="BNI",
                sender_excluded=True,
            )
        ],
        total_mutasi=195000,
    )
    res_excl_in = _post(client, headers, tab_type="normal", slot_a=[("in_excl.jpg", _image("in_excl"))])
    assert res_excl_in.status_code == 200
    assert res_excl_in.json()["errors"] == []

    # 3. Reimburse with Flip pair in Slot B must NOT double-sum Bank->Flip + Flip->Recipient
    vision["response"] = _payload(
        tab_type="reimburse",
        slot_a=[
            _slot_file(slot="A", filename="nota.jpg", amount=63000, document_type="cash_nota", company_account="Kas Operasional")
        ],
        slot_b=[
            _slot_file(slot="B", filename="b1.jpg", amount=63329, document_type="bank_transfer", sender_digits="1783680837", company_account="BNI"),
            _slot_file(slot="B", filename="b2.jpg", amount=63000, document_type="flip_to_recipient", sender_digits=None, company_account="BRI Operasional"),
        ],
        total_mutasi=63329,
        nominal_pokok=63000,
    )
    res_reim = _post(
        client,
        headers,
        tab_type="reimburse",
        slot_a=[("nota.jpg", _image("nota_bakso"))],
        slot_b=[("b1.jpg", _image("b1_bakso")), ("b2.jpg", _image("b2_bakso"))],
    )
    assert res_reim.status_code == 200
    body = res_reim.json()
    assert body["errors"] == []
    assert body["extracted"]["total_mutasi"] == 63329
    assert body["extracted"]["nominal_pokok"] == 63000
    assert body["extracted"]["biaya_admin_kode_unik"] == 329

