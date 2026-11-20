from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from app.core.security import require_menu
from app.schemas.auth import UserPublic
from app.schemas.rekonsiliasi import (
    RekonAutoRunRequest,
    RekonMatchRequest,
    RekonPenyesuaianRequest,
)
from app.services.excel_export import build_rekonsiliasi_cash_report_bytes
from app.services.rekonsiliasi_service import RekonError, rekonsiliasi_service
from app.services.storage import resolve_storage_path

router = APIRouter(prefix="/rekonsiliasi", tags=["Rekonsiliasi"])


@router.get("/metadata")
def get_rekonsiliasi_metadata(
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Daftar rekening, kategori SOP, dan daftar bulan yang tersedia untuk Rekonsiliasi."""
    return rekonsiliasi_service.get_metadata()


@router.get("/report")
def get_rekonsiliasi_report(
    rekening_id: int = Query(...),
    month: str = Query(...),
    saldo_awal: float | None = Query(None),
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Laporan Cash Report bulanan dan status rekonsiliasi mutasi bank per rekening."""
    try:
        return rekonsiliasi_service.get_report(
            rekening_id=rekening_id,
            month=month,
            saldo_awal_override=saldo_awal,
        )
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/export")
def export_rekonsiliasi_excel(
    rekening_id: int = Query(...),
    month: str = Query(...),
    saldo_awal: float | None = Query(None),
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> Response:
    """Unduh Cash Report bulanan per rekening dalam format Excel (.xlsx)."""
    try:
        report = rekonsiliasi_service.get_report(
            rekening_id=rekening_id,
            month=month,
            saldo_awal_override=saldo_awal,
        )
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    xlsx_bytes = build_rekonsiliasi_cash_report_bytes(report)
    filename = report["file_name"]
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/files/{filename}")
def serve_rekonsiliasi_file(
    filename: str,
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> FileResponse:
    """Menyajikan lampiran bukti transaksi untuk pengguna yang memiliki akses menu Rekonsiliasi."""
    try:
        path = resolve_storage_path(filename)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="File tidak ditemukan") from exc
    return FileResponse(path)


@router.post("/match")
def manual_match_rekonsiliasi(
    payload: RekonMatchRequest,
    current_user: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Menghubungkan secara manual 1 transaksi internal dengan 1..N baris mutasi bank."""
    try:
        return rekonsiliasi_service.manual_match(
            user=current_user,
            transaksi_id=payload.transaksi_id,
            mutasi_ids=payload.mutasi_ids,
            catatan=payload.catatan,
        )
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/match/{match_group_id}")
def unmatch_rekonsiliasi(
    match_group_id: str,
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Melepas tautan rekonsiliasi berdasarkan match_group_id."""
    try:
        return rekonsiliasi_service.unmatch(match_group_id=match_group_id)
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/penyesuaian")
def create_penyesuaian_mutasi(
    payload: RekonPenyesuaianRequest,
    current_user: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Mencatat baris mutasi bank yang belum punya struk menjadi PENYESUAIAN_MUTASI."""
    try:
        return rekonsiliasi_service.create_penyesuaian(user=current_user, payload=payload)
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/penyesuaian/{transaksi_id}")
def delete_penyesuaian_mutasi(
    transaksi_id: int,
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Menghapus transaksi penyesuaian mutasi dan mengembalikan status mutasi bank."""
    try:
        return rekonsiliasi_service.delete_penyesuaian(transaksi_id=transaksi_id)
    except RekonError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/auto-run")
def auto_run_rekonsiliasi(
    payload: RekonAutoRunRequest | None = None,
    _: UserPublic = Depends(require_menu("rekonsiliasi")),
) -> dict:
    """Menjalankan ulang auto-rekonsiliasi untuk transaksi yang belum cocok."""
    rekening_id = payload.rekening_id if payload else None
    return rekonsiliasi_service.auto_run(rekening_id=rekening_id)


@router.get("")
def get_rekonsiliasi(_: UserPublic = Depends(require_menu("rekonsiliasi"))) -> dict[str, str]:
    """Placeholder halaman Rekonsiliasi (akses dicek di tabel role_menus SQLite)."""
    return {"menu": "rekonsiliasi", "message": "halaman akan di kerjakan"}
