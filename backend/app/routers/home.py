from fastapi import APIRouter, Depends

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.services.home_service import home_service

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("")
def get_home(_: UserPublic = Depends(require_menu("home"))) -> dict:
    """Ringkasan rekening dan kategori SOP menu Home secara dinamis dari SQLite."""
    return home_service.get_home_data()
