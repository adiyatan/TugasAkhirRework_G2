from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import create_access_token, get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserPublic
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
