from fastapi import APIRouter, Depends

from app.core.security import require_menu
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/rekonsiliasi", tags=["Rekonsiliasi"])


@router.get("")
def get_rekonsiliasi(_: UserPublic = Depends(require_menu("rekonsiliasi"))) -> dict[str, str]:
    """Placeholder halaman Rekonsiliasi (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "rekonsiliasi", "message": "halaman akan di kerjakan"}
