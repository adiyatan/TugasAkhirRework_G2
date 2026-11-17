from fastapi import APIRouter, Depends

from app.core.security import require_menu
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/mutasi", tags=["Input Mutasi"])


@router.get("")
def get_mutasi(_: UserPublic = Depends(require_menu("input_mutasi"))) -> dict[str, str]:
    """Placeholder halaman Input Mutasi (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "input_mutasi", "message": "halaman akan di kerjakan"}
