from fastapi import APIRouter, Depends, Query

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.services.home_service import home_service

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("")
def get_home(
    bulan: str | None = Query(
        None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Filter bulan format YYYY-MM, mis. 2026-01. Kosong = semua periode.",
    ),
    _: UserPublic = Depends(require_menu("home")),
) -> dict:
    """Ringkasan rekening dan kategori SOP menu Home secara dinamis dari SQLite."""
    return home_service.get_home_data(bulan=bulan)
