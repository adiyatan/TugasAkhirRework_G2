from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import create_access_token, get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserPublic
from app.seed import reset_transactional_data, seed_januari_2026
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """Login menggunakan username & password untuk mendapatkan Bearer token dan role."""
    user = auth_service.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
        )
    token = create_access_token(user)
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserPublic)
def get_me(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    """Mengambil profil dan role user yang sedang login."""
    return current_user


@router.post("/reset-seed")
def reset_seed_data() -> dict:
    """Mereset seluruh data transaksi, mutasi, rekonsiliasi, dan file gambar ke seed Januari 2026."""
    try:
        result = seed_januari_2026(reset=True)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    total_mutasi = result["bni_inserted"] + result["bri_inserted"]
    return {
        "message": (
            "Data berhasil di-reset ke seed Januari 2026 "
            f"({result['transaksi_internal_count']} transaksi, "
            f"{total_mutasi} baris mutasi, "
            f"{result['file_bukti_count']} file bukti)."
        ),
        **result,
    }


@router.post("/reset-empty")
def reset_empty_data() -> dict:
    """Mereset seluruh data transaksi, mutasi, rekonsiliasi, dan file gambar tanpa mengisi seed."""
    reset_transactional_data()
    return {
        "seeded": False,
        "message": "Database & gambar berhasil di-reset menjadi kosong (tanpa seed).",
    }
