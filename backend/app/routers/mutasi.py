from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.schemas.mutasi import MutasiMetadata, MutasiSaveRequest
from app.services.mutasi_service import MutasiError, mutasi_service

router = APIRouter(prefix="/mutasi", tags=["Input Mutasi"])


@router.get("/metadata", response_model=MutasiMetadata)
def get_mutasi_metadata(
    _: UserPublic = Depends(require_menu("input_mutasi")),
) -> MutasiMetadata:
    """Daftar rekening perusahaan non-tunai aktif untuk upload mutasi PDF."""
    return mutasi_service.get_metadata()


@router.post("/preview")
async def preview_mutasi(
    file: UploadFile = File(...),
    rekening_id: str | None = Form(None),
    _: UserPublic = Depends(require_menu("input_mutasi")),
) -> dict:
    """Upload PDF mutasi dan ekstrak preview transaksi beserta cek saldo."""
    parsed_rekening_id: int | None = None
    if rekening_id is not None and rekening_id.strip() and rekening_id.strip().upper() != "AUTO":
        try:
            parsed_rekening_id = int(rekening_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="rekening_id tidak valid") from exc

    data = await file.read()
    try:
        return await mutasi_service.preview(
            filename=file.filename or "mutasi.pdf",
            data=data,
            rekening_id=parsed_rekening_id,
        )
    except MutasiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/save")
def save_mutasi(
    payload: MutasiSaveRequest,
    current_user: UserPublic = Depends(require_menu("input_mutasi")),
) -> dict:
    """Simpan batch mutasi PDF terverifikasi dan jalankan rekonsiliasi otomatis."""
    try:
        return mutasi_service.save(user=current_user, payload=payload)
    except MutasiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/batches")
def list_mutasi_batches(
    rekening_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: UserPublic = Depends(require_menu("input_mutasi")),
) -> dict:
    """Daftar riwayat batch PDF mutasi yang sudah diunggah."""
    return mutasi_service.list_batches(rekening_id=rekening_id, limit=limit)


@router.get("/rows")
def list_mutasi_rows(
    rekening_id: int | None = Query(None),
    batch_id: int | None = Query(None),
    status_rekonsiliasi: str | None = Query(None),
    tipe: str | None = Query(None),
    tanggal_mulai: str | None = Query(None),
    tanggal_selesai: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    _: UserPublic = Depends(require_menu("input_mutasi")),
) -> dict:
    """Daftar baris mutasi bank dengan filter rekening, batch, periode, tipe, dan status."""
    return mutasi_service.list_rows(
        rekening_id=rekening_id,
        batch_id=batch_id,
        status_rekonsiliasi=status_rekonsiliasi,
        tipe=tipe,
        tanggal_mulai=tanggal_mulai,
        tanggal_selesai=tanggal_selesai,
        search=search,
        limit=limit,
    )


@router.delete("/batches/{batch_id}")
def delete_mutasi_batch(
    batch_id: int,
    _: UserPublic = Depends(require_menu("input_mutasi")),
) -> dict:
    """Hapus batch mutasi dan hitung ulang status transaksi internal yang terdampak."""
    try:
        return mutasi_service.delete_batch(batch_id=batch_id)
    except MutasiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("")
def get_mutasi(_: UserPublic = Depends(require_menu("input_mutasi"))) -> dict[str, str]:
    """Placeholder halaman Input Mutasi (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "input_mutasi", "message": "halaman akan di kerjakan"}
