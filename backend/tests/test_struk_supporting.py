from pathlib import Path

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
            "bahan": conn.execute("SELECT id FROM kategori_sop WHERE nama_kategori = 'Bahan Baku'").fetchone()["id"],
        }


def _make_transaction(
    *,
    username: str = "staff",
    total: int = 75000,
    status_rekonsiliasi: str = "BELUM_REKON",
    filename: str = "proof.jpg",
    file_data: bytes = b"proof-image",
) -> tuple[int, str]:
    ids = _ids()
    storage.ensure_storage_layout()
    (storage.storage_root() / "files" / filename).write_bytes(file_data)
    with get_connection() as conn:
        tx_id = conn.execute(
            """
            INSERT INTO transaksi_internal (
                created_by_user_id, nama_admin, tanggal_input, tab_type,
                tanggal_transaksi, waktu_transaksi, rekening_sumber_id, tipe,
                kategori_id, penerima_pengirim, keterangan, nominal_pokok,
                biaya_admin_kode_unik, total_mutasi, status_rekonsiliasi
            ) VALUES (?, 'Tim Staff', '2026-01-09', 'normal',
                '2026-01-09', '14:10:00', ?, 'KELUAR', ?, 'Toko Contoh',
                'Pembelian bahan baku', ?, 0, ?, ?)
            """,
            (
                ids[username],
                ids["bni"],
                ids["bahan"],
                total,
                total,
                status_rekonsiliasi,
            ),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO file_bukti_log (
                transaksi_internal_id, slot, filename, orig_filename, file_hash,
                jenis_struk, status_file
            ) VALUES (?, 'A', ?, ?, ?, 'bank_transfer', 'TERPAKAI_UTAMA')
            """,
            (tx_id, filename, filename, f"hash-{filename}-{tx_id}"),
        )
        conn.commit()
    return tx_id, filename


def test_recent_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/struk/recent").status_code == 401


def test_recent_respects_staff_visibility_and_includes_attachments(client: TestClient) -> None:
    own_id, own_file = _make_transaction(username="staff", filename="own.jpg")
    other_id, _ = _make_transaction(username="finance", filename="other.jpg")

    staff_headers = _login(client, "staff", "staff123")
    staff_response = client.get("/api/v1/struk/recent", headers=staff_headers)
    assert staff_response.status_code == 200
    staff_items = staff_response.json()["items"]
    assert [item["id"] for item in staff_items] == [own_id]
    assert staff_items[0]["files"][0]["filename"] == own_file
    assert staff_items[0]["files"][0]["url"] == f"/api/v1/struk/files/{own_file}"

    finance_headers = _login(client, "finance", "finance123")
    finance_response = client.get("/api/v1/struk/recent", headers=finance_headers)
    assert finance_response.status_code == 200
    finance_ids = {item["id"] for item in finance_response.json()["items"]}
    assert finance_ids == {own_id, other_id}


def test_recent_rejects_invalid_limit(client: TestClient) -> None:
    headers = _login(client)

    assert client.get("/api/v1/struk/recent?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/struk/recent?limit=101", headers=headers).status_code == 422


def test_staff_delete_only_own_unreconciled_transaction(client: TestClient) -> None:
    headers = _login(client, "staff", "staff123")
    own_id, _ = _make_transaction(username="staff")
    other_id, _ = _make_transaction(username="finance", filename="other.jpg")
    reconciled_id, _ = _make_transaction(
        username="staff",
        status_rekonsiliasi="SESUAI",
        filename="reconciled.jpg",
    )

    assert client.delete(f"/api/v1/struk/{other_id}", headers=headers).status_code == 403
    assert client.delete(f"/api/v1/struk/{reconciled_id}", headers=headers).status_code == 403
    assert client.delete(f"/api/v1/struk/{own_id}", headers=headers).status_code == 200


def test_finance_can_delete_any_transaction_and_files_are_removed(client: TestClient) -> None:
    headers = _login(client, "finance", "finance123")
    tx_id, filename = _make_transaction(username="staff", status_rekonsiliasi="SESUAI")
    path = storage.storage_root() / "files" / filename
    assert path.is_file()

    response = client.delete(f"/api/v1/struk/{tx_id}", headers=headers)

    assert response.status_code == 200
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM transaksi_internal").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM file_bukti_log").fetchone()[0] == 0
    assert not path.exists()


def test_delete_unknown_transaction_returns_404(client: TestClient) -> None:
    headers = _login(client, "finance", "finance123")

    assert client.delete("/api/v1/struk/99999", headers=headers).status_code == 404


def test_file_endpoint_serves_only_safe_existing_files(client: TestClient) -> None:
    headers = _login(client)
    _, filename = _make_transaction(filename="serve.jpg", file_data=b"png-bytes")

    response = client.get(f"/api/v1/struk/files/{filename}", headers=headers)

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"].startswith("image/")


def test_file_endpoint_requires_auth_and_blocks_traversal(client: TestClient) -> None:
    headers = _login(client)
    storage.ensure_storage_layout()
    secret = storage.storage_root() / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    assert client.get("/api/v1/struk/files/serve.jpg").status_code == 401
    assert client.get("/api/v1/struk/files/../secret.txt", headers=headers).status_code in {400, 404}
    assert client.get("/api/v1/struk/files/missing.jpg", headers=headers).status_code == 404
