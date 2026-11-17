from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.routers import auth, home, mutasi, rekonsiliasi, struk


def create_app() -> FastAPI:
    """Factory untuk membuat instance FastAPI."""
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

    return app


app = create_app()
