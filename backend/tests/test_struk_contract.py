from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings, settings
from app.core.database import init_db
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


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_struk_metadata_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/struk/metadata")

    assert response.status_code == 401


def test_struk_metadata_returns_database_master_data(client: TestClient) -> None:
    headers = _login(client, "staff", "staff123")

    response = client.get("/api/v1/struk/metadata", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["rekening_perusahaan"]) == 5
    assert len(body["kategori_sop"]) == 14
    assert len(body["rekening_dikecualikan"]) == 1
    assert {row["kode_akun"] for row in body["rekening_perusahaan"]} >= {"BNI", "BRI"}
    cash_rows = [row for row in body["rekening_perusahaan"] if row["is_cash"]]
    assert [row["kode_akun"] for row in cash_rows] == ["Kas Operasional"]


def test_runtime_prompt_is_packaged_with_backend() -> None:
    prompt_path = Path(__file__).resolve().parents[1] / "app" / "prompts" / "receipt_extraction.prompt.md"

    assert prompt_path.is_file()
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "{{TAB_TYPE}}" in prompt
    assert "{{KATEGORI_SOP}}" in prompt


def test_vision_model_defaults_and_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.setattr(settings, "vision_model", "gemini/gemini-2.5-flash")
    assert settings.vision_model == "gemini/gemini-2.5-flash"

    monkeypatch.setenv("VISION_MODEL", "openai/gpt-4o-mini")
    assert Settings().vision_model == "openai/gpt-4o-mini"


def test_storage_rejects_path_traversal_and_unknown_files(tmp_path: Path) -> None:
    root = storage.ensure_storage_layout()

    with pytest.raises(ValueError):
        storage.resolve_storage_path("../secret.txt")
    with pytest.raises(ValueError):
        storage.resolve_storage_path(str(tmp_path / "absolute.txt"))
    with pytest.raises(ValueError):
        storage.resolve_storage_path("nested/file.jpg")
    with pytest.raises(FileNotFoundError):
        storage.resolve_storage_path("missing.jpg")

    valid = root / "files" / "safe.jpg"
    valid.parent.mkdir(parents=True, exist_ok=True)
    valid.write_bytes(b"image")
    assert storage.resolve_storage_path("safe.jpg") == valid


def test_upload_validation_checks_content_type_and_size() -> None:
    storage.validate_upload("receipt.jpg", "image/jpeg", b"jpeg-bytes")
    storage.validate_upload("receipt.jpeg", "image/jpeg", b"jpeg-bytes")
    storage.validate_upload("receipt.png", "image/png", b"png-bytes")
    storage.validate_upload("receipt.webp", "image/webp", b"webp-bytes")
    storage.validate_upload("receipt.heic", "image/heic", b"heic-bytes")

    with pytest.raises(storage.UploadValidationError):
        storage.validate_upload("receipt.txt", "text/plain", b"not an image")
    with pytest.raises(storage.UploadValidationError):
        storage.validate_upload("receipt.jpg", "image/jpeg", b"x" * (settings.max_upload_mb * 1024 * 1024 + 1))
