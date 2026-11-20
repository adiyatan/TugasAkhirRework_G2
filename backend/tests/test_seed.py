from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import seed
from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app


@pytest.fixture()
def isolated_seed_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "seed_test.db"
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "storage_dir", str(storage_dir))
    return tmp_path


def test_seed_only_if_empty_and_reset(isolated_seed_env: Path) -> None:
    assert seed.is_database_empty() is True

    first = seed.seed_januari_2026(only_if_empty=True)
    assert first["seeded"] is True
    assert first["bni_inserted"] == 84
    assert first["bri_inserted"] == 14
    assert first["transaksi_internal_count"] == 68
    assert first["file_bukti_count"] == 111
    assert seed.is_database_empty() is False

    stored_files = list((isolated_seed_env / "storage" / "files").glob("*.jpg"))
    assert len(stored_files) == 111

    second = seed.seed_januari_2026(only_if_empty=True)
    assert second == {"seeded": False, "reason": "database_not_empty"}

    with pytest.raises(RuntimeError):
        seed.seed_januari_2026(reset=False, only_if_empty=False)

    reseeded = seed.seed_januari_2026(reset=True)
    assert reseeded["seeded"] is True
    assert reseeded["transaksi_internal_count"] == 68
    assert reseeded["file_bukti_count"] == 111

    with closing(get_connection()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM mutasi_upload_batch").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM mutasi_bank").fetchone()[0] == 98
        assert conn.execute("SELECT COUNT(*) FROM transaksi_internal").fetchone()[0] == 68
        assert conn.execute("SELECT COUNT(*) FROM file_bukti_log").fetchone()[0] == 111
        pindah_rows = conn.execute(
            "SELECT rekening_sumber_id, rekening_tujuan_id FROM transaksi_internal WHERE tipe = 'PINDAH_BUKU'"
        ).fetchall()
        assert len(pindah_rows) == 5
        assert all(r["rekening_tujuan_id"] is not None for r in pindah_rows)


def test_seed_cli_and_api_attachment_serving(isolated_seed_env: Path) -> None:
    init_db()
    seed.main(["--if-empty"])
    assert seed.is_database_empty() is False

    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "finance", "password": "finance123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    recent = client.get("/api/v1/struk/recent?limit=100", headers=headers)
    assert recent.status_code == 200
    items = recent.json()["items"]
    assert len(items) == 68
    reimburse_items = [item for item in items if item["tab_type"] == "reimburse"]
    assert len(reimburse_items) == 4
    for item in reimburse_items:
        assert len(item["files"]) >= 2
        for f in item["files"]:
            file_res = client.get(f["url"], headers=headers)
            assert file_res.status_code == 200
            assert file_res.headers["content-type"].startswith("image/")

    # Simulate missing storage/files on existing DB (like cloning repo without storage/)
    target_file = isolated_seed_env / "storage" / "files" / reimburse_items[0]["files"][0]["filename"]
    target_file.unlink()
    assert not target_file.exists()
    res_restore = seed.seed_januari_2026(only_if_empty=True)
    assert res_restore["seeded"] is False
    assert res_restore["restored_files"] == 1
    assert target_file.is_file()

    report = client.get("/api/v1/rekonsiliasi/report?rekening_id=1&month=2026-01", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["summary"]["mutasi_total"] == 84


def test_auth_reset_seed_endpoint(isolated_seed_env: Path) -> None:
    init_db()
    files_dir = isolated_seed_env / "storage" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    stray_file = files_dir / "stray_uploaded_image.jpg"
    stray_file.write_bytes(b"stray-image")

    client = TestClient(app)
    res = client.post("/api/v1/auth/reset-seed")
    assert res.status_code == 200
    body = res.json()
    assert body["seeded"] is True
    assert body["transaksi_internal_count"] == 68
    assert body["bni_inserted"] == 84
    assert body["bri_inserted"] == 14
    assert body["file_bukti_count"] == 111
    assert not stray_file.exists()
    assert len(list(files_dir.glob("*.jpg"))) == 111


def test_auth_reset_empty_endpoint(isolated_seed_env: Path) -> None:
    seed.seed_januari_2026(only_if_empty=True)
    assert seed.is_database_empty() is False
    files_dir = isolated_seed_env / "storage" / "files"
    assert len(list(files_dir.glob("*.jpg"))) == 111

    client = TestClient(app)
    res = client.post("/api/v1/auth/reset-empty")
    assert res.status_code == 200
    body = res.json()
    assert body["seeded"] is False
    assert seed.is_database_empty() is True
    assert list(files_dir.glob("*")) == []

    with closing(get_connection()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM rekening_perusahaan").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM kategori_sop").fetchone()[0] == 14
