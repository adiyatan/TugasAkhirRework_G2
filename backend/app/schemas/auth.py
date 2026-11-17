from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Schema request untuk login."""

    username: str = Field(..., min_length=1, examples=["finance"])
    password: str = Field(..., min_length=1, examples=["finance123"])


class UserPublic(BaseModel):
    """Data user beserta role dan daftar menu yang diizinkan dari SQLite."""

    username: str
    full_name: str
    role: str
    allowed_menus: list[str]


class TokenResponse(BaseModel):
    """Response setelah login berhasil."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic
