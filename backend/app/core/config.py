import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> Path | None:
    """Gunakan .env hanya jika flag --env-file <path> diberikan."""
    args = sys.argv
    for index, arg in enumerate(args):
        if arg == "--env-file":
            if index + 1 >= len(args):
                return None
            raw_path = args[index + 1]
        elif arg.startswith("--env-file="):
            raw_path = arg.split("=", 1)[1]
        else:
            continue
        if not raw_path or raw_path.startswith("--"):
            return None
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return None


class Settings(BaseSettings):
    """Konfigurasi aplikasi dari environment; .env hanya jika --env-file diberikan."""

    app_name: str = "FastAPI Simple App"
    api_prefix: str = "/api/v1"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    token_expire_minutes: int = 60
    database_path: str = "app.db"
    storage_dir: str = "storage"
    max_upload_mb: int = 10
    staging_ttl_minutes: int = 120
    vision_model: str = "gemini/gemini-3.5-flash-lite"
    vision_api_key: str | None = None
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    model_config = SettingsConfigDict(
        # Tidak ada pembacaan .env default.
        # Gunakan `python -m app --env-file <path>` untuk memilih file .env.
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
