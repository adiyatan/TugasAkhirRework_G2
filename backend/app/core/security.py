import base64
from collections.abc import Callable
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.schemas.auth import UserPublic
from app.services.auth_service import auth_service

bearer_scheme = HTTPBearer(auto_error=False)


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(user: UserPublic) -> str:
    """Membuat token HMAC-SHA256 sederhana berisi info user dan waktu kadaluarsa."""
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": int(time.time()) + (settings.token_expire_minutes * 60),
    }
    payload_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}.{_b64_encode(signature)}"


def decode_access_token(token: str) -> UserPublic:
    """Memvalidasi tanda tangan, masa berlaku token, dan mengambil user terbaru dari SQLite."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid") from exc

    expected_sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64_encode(expected_sig), sig_b64):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature token tidak valid")

    try:
        payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
        if int(payload["exp"]) < int(time.time()):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sudah kedaluwarsa")
        username = payload["sub"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Payload token tidak valid") from exc

    user = auth_service.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User tidak ditemukan")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserPublic:
    """Dependency untuk mengambil user yang sedang login dari header Authorization."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi diperlukan",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


def require_menu(menu_key: str) -> Callable[[UserPublic], UserPublic]:
    """Dependency factory untuk mengecek izin menu user berdasarkan role di SQLite."""

    def _menu_checker(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
        if not auth_service.has_menu_access(current_user.role, menu_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akses ditolak. Role '{current_user.role}' tidak memiliki izin ke menu '{menu_key}'.",
            )
        return current_user

    return _menu_checker
