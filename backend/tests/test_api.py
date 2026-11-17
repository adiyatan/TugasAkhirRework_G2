from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.core.database import get_connection, init_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Menggunakan database SQLite terpisah untuk setiap test."""
    test_db = tmp_path / "test_app.db"
    monkeypatch.setattr(settings, "database_path", str(test_db))
    init_db()


client = TestClient(app)


def _login(username: str, password: str) -> tuple[dict[str, str], dict]:
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sqlite_seeded_roles_and_menu_permissions() -> None:
    assert client.get("/api/v1/struk").status_code == 401

    bad_res = client.post(
        "/api/v1/auth/login",
        json={"username": "finance", "password": "wrong"},
    )
    assert bad_res.status_code == 401

    staff_headers, staff_user = _login("staff", "staff123")
    assert staff_user["role"] == "staff"
    assert staff_user["allowed_menus"] == ["input_struk"]

    me_res = client.get("/api/v1/auth/me", headers=staff_headers)
    assert me_res.status_code == 200
    assert me_res.json()["allowed_menus"] == ["input_struk"]

    _, mgmt_user = _login("management", "management123")
    assert mgmt_user["allowed_menus"] == ["home", "input_struk", "input_mutasi", "rekonsiliasi"]

    _, fin_user = _login("finance", "finance123")
    assert fin_user["allowed_menus"] == ["home", "input_struk", "input_mutasi", "rekonsiliasi"]


def test_staff_only_allowed_input_struk() -> None:
    staff_headers, _ = _login("staff", "staff123")

    struk_res = client.get("/api/v1/struk", headers=staff_headers)
    assert struk_res.status_code == 200
    assert struk_res.json() == {"menu": "input_struk", "message": "halaman akan di kerjakan"}

    assert client.get("/api/v1/home", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/mutasi", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/rekonsiliasi", headers=staff_headers).status_code == 403


def test_management_and_finance_can_access_all_menus() -> None:
    for username, password in [("management", "management123"), ("finance", "finance123")]:
        headers, _ = _login(username, password)

        home_res = client.get("/api/v1/home", headers=headers)
        assert home_res.status_code == 200
        home_data = home_res.json()
        assert home_data["perusahaan"] == "PT Lokal Komoditi Indonesia"
        assert len(home_data["rekening"]) == 5
        assert len(home_data["kategori"]) == 14

        for endpoint, menu_key in [
            ("/api/v1/struk", "input_struk"),
            ("/api/v1/mutasi", "input_mutasi"),
            ("/api/v1/rekonsiliasi", "rekonsiliasi"),
        ]:
            res = client.get(endpoint, headers=headers)
            assert res.status_code == 200
            assert res.json() == {"menu": menu_key, "message": "halaman akan di kerjakan"}


def test_dynamic_permission_change_in_sqlite() -> None:
    staff_headers, _ = _login("staff", "staff123")
    assert client.get("/api/v1/home", headers=staff_headers).status_code == 403

    with get_connection() as conn:
        role_row = conn.execute("SELECT id FROM roles WHERE name = 'staff'").fetchone()
        conn.execute(
            "INSERT INTO role_menus (role_id, menu_key) VALUES (?, ?)",
            (role_row["id"], "home"),
        )
        conn.commit()

    assert client.get("/api/v1/home", headers=staff_headers).status_code == 200
