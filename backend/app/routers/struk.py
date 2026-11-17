from fastapi import APIRouter, Depends

from app.core.security import require_menu
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/struk", tags=["Input Struk"])


@router.get("")
def get_struk(_: UserPublic = Depends(require_menu("input_struk"))) -> dict[str, str]:
    """Placeholder halaman Input Struk (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "input_struk", "message": "halaman akan di kerjakan"}
