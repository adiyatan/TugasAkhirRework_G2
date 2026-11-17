from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.routers import auth, home, mutasi, rekonsiliasi, struk

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production"


def create_app() -> FastAPI:
    """Factory untuk membuat instance FastAPI."""
    if not settings.debug and settings.secret_key == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY masih memakai nilai default. Set SECRET_KEY melalui environment "
            "atau .env sebelum menjalankan aplikasi non-debug."
        )

    init_db()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    # Izinkan UI terpisah mengakses API backend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(home.router, prefix=settings.api_prefix)
    app.include_router(struk.router, prefix=settings.api_prefix)
    app.include_router(mutasi.router, prefix=settings.api_prefix)
    app.include_router(rekonsiliasi.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["Health"])
    def health_check() -> dict[str, str]:
        """Endpoint untuk mengecek status server."""
        return {"status": "ok", "app": settings.app_name}

    # Sajikan UI statis dari origin yang sama (dipasang paling akhir agar API & docs tetap menang).
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
