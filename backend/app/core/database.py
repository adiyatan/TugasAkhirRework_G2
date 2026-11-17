from pathlib import Path
import sqlite3

from app.core.config import settings
from app.core.password import hash_password

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ROLE_MENUS: dict[str, list[str]] = {
    "management": ["home", "input_struk", "input_mutasi", "rekonsiliasi"],
    "finance": ["home", "input_struk", "input_mutasi", "rekonsiliasi"],
    "staff": ["input_struk"],
}

DEFAULT_USERS: list[tuple[str, str, str, str]] = [
    ("management", "Tim Management", "management123", "management"),
    ("finance", "Tim Finance", "finance123", "finance"),
    ("staff", "Tim Staff", "staff123", "staff"),
]


def get_db_path() -> Path:
    """Mengembalikan path absolut file SQLite."""
    db_path = Path(settings.database_path)
    if not db_path.is_absolute():
        return BACKEND_ROOT / db_path
    return db_path


def get_connection() -> sqlite3.Connection:
    """Membuka koneksi SQLite dengan Row factory dan foreign keys aktif."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Membuat tabel roles, role_menus, users dan mengisi data awal jika belum ada."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS role_menus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                menu_key TEXT NOT NULL,
                UNIQUE(role_id, menu_key)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL REFERENCES roles(id)
            );
            """
        )

        for role_name, menus in DEFAULT_ROLE_MENUS.items():
            conn.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role_name,))
            role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
            role_id = role_row["id"]
            for menu_key in menus:
                conn.execute(
                    "INSERT OR IGNORE INTO role_menus (role_id, menu_key) VALUES (?, ?)",
                    (role_id, menu_key),
                )

        for username, full_name, raw_password, role_name in DEFAULT_USERS:
            role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
            if role_row:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (username, full_name, password_hash, role_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, full_name, hash_password(raw_password), role_row["id"]),
                )

        conn.commit()
