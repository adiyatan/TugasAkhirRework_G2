from app.core.database import get_connection
from app.core.password import verify_password
from app.schemas.auth import UserPublic


class AuthService:
    """Service autentikasi dan pengecekan hak akses menu berbasis SQLite."""

    def get_menus_for_role(self, role_name: str) -> list[str]:
        """Mengambil daftar menu yang diizinkan untuk suatu role dari SQLite."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT rm.menu_key
                FROM role_menus rm
                JOIN roles r ON r.id = rm.role_id
                WHERE r.name = ?
                ORDER BY rm.id ASC
                """,
                (role_name,),
            ).fetchall()
        return [row["menu_key"] for row in rows]

    def has_menu_access(self, role_name: str, menu_key: str) -> bool:
        """Mengecek apakah role memiliki akses ke menu tertentu di SQLite."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM role_menus rm
                JOIN roles r ON r.id = rm.role_id
                WHERE r.name = ? AND rm.menu_key = ?
                LIMIT 1
                """,
                (role_name, menu_key),
            ).fetchone()
        return row is not None

    def get_user_by_username(self, username: str) -> UserPublic | None:
        """Mengambil profil user beserta role dan menu aksesnya dari SQLite."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.username, u.full_name, r.name AS role_name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE u.username = ?
                """,
                (username.strip().lower(),),
            ).fetchone()
        if not row:
            return None
        role_name = row["role_name"]
        return UserPublic(
            username=row["username"],
            full_name=row["full_name"],
            role=role_name,
            allowed_menus=self.get_menus_for_role(role_name),
        )

    def authenticate(self, username: str, password: str) -> UserPublic | None:
        """Memverifikasi username dan password terhadap tabel users di SQLite."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.username, u.full_name, u.password_hash, r.name AS role_name
                FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE u.username = ?
                """,
                (username.strip().lower(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        role_name = row["role_name"]
        return UserPublic(
            username=row["username"],
            full_name=row["full_name"],
            role=role_name,
            allowed_menus=self.get_menus_for_role(role_name),
        )


auth_service = AuthService()
