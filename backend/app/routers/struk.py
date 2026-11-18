from fastapi import APIRouter, Depends

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.schemas.struk import StrukMetadata
from app.services.struk_service import struk_service

router = APIRouter(prefix="/struk", tags=["Input Struk"])


@router.get("/metadata", response_model=StrukMetadata)
def get_metadata(_: UserPublic = Depends(require_menu("input_struk"))) -> StrukMetadata:
    """Mengambil data master form Input Struk dari SQLite."""
    return struk_service.get_metadata()


@router.get("")
def get_struk(_: UserPublic = Depends(require_menu("input_struk"))) -> dict[str, str]:
    """Placeholder halaman Input Struk (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "input_struk", "message": "halaman akan di kerjakan"}
