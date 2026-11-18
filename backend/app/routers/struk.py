from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.schemas.struk import StrukMetadata, StrukSaveRequest
from app.services.storage import resolve_storage_path
from app.services.struk_service import ReceiptUpload, StrukError, struk_service

router = APIRouter(prefix="/struk", tags=["Input Struk"])


async def _read_uploads(slot: str, files: list[UploadFile] | None) -> list[ReceiptUpload]:
    uploads: list[ReceiptUpload] = []
    for file in files or []:
        uploads.append(
            ReceiptUpload(
                slot=slot,
                filename=file.filename or f"{slot.lower()}.jpg",
                content_type=file.content_type or "",
                data=await file.read(),
            )
        )
    return uploads


@router.get("/metadata", response_model=StrukMetadata)
def get_metadata(_: UserPublic = Depends(require_menu("input_struk"))) -> StrukMetadata:
    """Mengambil data master form Input Struk dari SQLite."""
    return struk_service.get_metadata()


@router.post("/extract")
async def extract_struk(
    tab_type: str = Form(...),
    is_cash: bool = Form(False),
    slot_a: list[UploadFile] | None = File(None),
    slot_b: list[UploadFile] | None = File(None),
    slot_c: list[UploadFile] | None = File(None),
    current_user: UserPublic = Depends(require_menu("input_struk")),
) -> dict:
    """Ekstraksi batch struk menjadi satu kandidat transaksi."""
    try:
        return await struk_service.extract(
            user=current_user,
            tab_type=tab_type,
            is_cash=is_cash,
            slot_a=await _read_uploads("A", slot_a),
            slot_b=await _read_uploads("B", slot_b),
            slot_c=await _read_uploads("C", slot_c),
        )
    except StrukError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc


@router.post("/save")
def save_struk(
    payload: StrukSaveRequest,
    current_user: UserPublic = Depends(require_menu("input_struk")),
) -> dict:
    """Menyimpan hasil review menjadi satu transaksi dan 1..N file bukti."""
    try:
        return struk_service.save(user=current_user, payload=payload)
    except StrukError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc


@router.get("/recent")
def recent_struk(
    limit: int = Query(20, ge=1, le=100),
    current_user: UserPublic = Depends(require_menu("input_struk")),
) -> dict:
    """Riwayat transaksi Input Struk beserta lampirannya."""
    return struk_service.list_recent(user=current_user, limit=limit)


@router.get("/files/{filename}")
def serve_struk_file(
    filename: str,
    _: UserPublic = Depends(require_menu("input_struk")),
) -> FileResponse:
    """Menyajikan file bukti dengan proteksi path traversal."""
    try:
        path = resolve_storage_path(filename)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File tidak ditemukan") from exc
    return FileResponse(path)


@router.delete("/{transaksi_id}")
def delete_struk(
    transaksi_id: int,
    current_user: UserPublic = Depends(require_menu("input_struk")),
) -> dict:
    """Menghapus transaksi Input Struk sesuai kontrol role dan status rekonsiliasi."""
    try:
        return struk_service.delete(user=current_user, transaksi_id=transaksi_id)
    except StrukError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc


@router.get("")
def get_struk(_: UserPublic = Depends(require_menu("input_struk"))) -> dict[str, str]:
    """Placeholder halaman Input Struk (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "input_struk", "message": "halaman akan di kerjakan"}
