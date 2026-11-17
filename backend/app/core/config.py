from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi aplikasi yang dibaca dari file .env atau environment variables."""

    app_name: str = "FastAPI Simple App"
    api_prefix: str = "/api/v1"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"
    token_expire_minutes: int = 60
    database_path: str = "app.db"
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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
