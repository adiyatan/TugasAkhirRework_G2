from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_menu
from app.schemas.ai import AiEvaluateRequest, AiModelSwitchRequest
from app.schemas.auth import UserPublic
from app.services.ai_service import AiServiceError, ai_service

router = APIRouter(prefix="/ai", tags=["AI Governance & Evaluation"])


@router.get("/overview")
def get_ai_overview(_: UserPublic = Depends(require_menu("ai_settings"))) -> dict:
    """Mengambil model aktif, katalog harga, ringkasan token/biaya, dan riwayat evaluasi (khusus Management)."""
    return ai_service.get_overview()


@router.put("/model")
def switch_ai_model(
    payload: AiModelSwitchRequest,
    current_user: UserPublic = Depends(require_menu("ai_settings")),
) -> dict:
    """Memindahkan model Vision AI aktif secara persisten di SQLite (khusus Management)."""
    try:
        return ai_service.switch_model(
            user=current_user,
            model=payload.model,
            usd_to_idr_rate=payload.usd_to_idr_rate,
        )
    except AiServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/evaluate")
async def evaluate_ai_model(
    payload: AiEvaluateRequest,
    current_user: UserPublic = Depends(require_menu("ai_settings")),
) -> dict:
    """Menjalankan evaluasi offline pada Golden Dataset untuk menguji kualitas model kandidat."""
    try:
        return await ai_service.evaluate_model(
            user=current_user,
            candidate_model=payload.candidate_model,
            sample_size=payload.sample_size,
            compare_baseline=payload.compare_baseline,
        )
    except AiServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/evaluations")
def list_ai_evaluations(
    limit: int = Query(20, ge=1, le=50),
    _: UserPublic = Depends(require_menu("ai_settings")),
) -> dict:
    """Daftar riwayat evaluasi model AI."""
    return ai_service.list_evaluations(limit=limit)


@router.get("/evaluations/{run_id}")
def get_ai_evaluation(
    run_id: int,
    _: UserPublic = Depends(require_menu("ai_settings")),
) -> dict:
    """Detail hasil evaluasi model AI per kasus Golden Dataset."""
    try:
        return ai_service.get_evaluation(run_id=run_id)
    except AiServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
