from __future__ import annotations

from pathlib import Path
import re

from app.core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
ALLOWED_SUBDIRS = {"files", "staging"}


class UploadValidationError(ValueError):
    """Raised when an uploaded file is not an acceptable receipt image."""


def storage_root() -> Path:
    path = Path(settings.storage_dir)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path


def ensure_storage_layout() -> Path:
    root = storage_root()
    (root / "files").mkdir(parents=True, exist_ok=True)
    (root / "staging").mkdir(parents=True, exist_ok=True)
    return root


def _validate_name(filename: str) -> str:
    if not filename or filename in {".", ".."}:
        raise ValueError("filename tidak valid")
    if Path(filename).is_absolute() or filename != Path(filename).name:
        raise ValueError("filename tidak boleh berisi path")
    if "/" in filename or "\\" in filename or "\x00" in filename or ".." in filename:
        raise ValueError("filename tidak valid")
    return filename


def resolve_storage_path(filename: str, subdir: str = "files") -> Path:
    if subdir not in ALLOWED_SUBDIRS:
        raise ValueError("subdir penyimpanan tidak valid")
    safe_name = _validate_name(filename)
    root = ensure_storage_layout()
    base = (root / subdir).resolve()
    candidate = (base / safe_name).resolve()
    if candidate.parent != base:
        raise ValueError("path keluar dari direktori penyimpanan")
    if not candidate.is_file():
        raise FileNotFoundError(safe_name)
    return candidate


def validate_upload(filename: str, content_type: str, data: bytes) -> None:
    _validate_name(filename)
    if not data:
        raise UploadValidationError("File kosong")
    if content_type.lower() not in ALLOWED_IMAGE_TYPES:
        raise UploadValidationError("Format file harus berupa gambar JPEG, PNG, WEBP, atau HEIC")
    max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    if len(data) > max_bytes:
        raise UploadValidationError(f"Ukuran file melebihi {settings.max_upload_mb} MB")


def safe_stored_filename(original_filename: str, file_hash: str, slot: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".jpg"
    return f"{file_hash[:24]}_{slot.upper()}{suffix}"


def write_staging_file(staging_id: str, filename: str, data: bytes) -> Path:
    safe_staging_id = _validate_name(staging_id)
    folder = ensure_storage_layout() / "staging" / safe_staging_id
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / _validate_name(filename)
    destination.write_bytes(data)
    return destination


def move_to_permanent(staging_path: Path, stored_filename: str) -> Path:
    files_dir = ensure_storage_layout() / "files"
    destination = files_dir / _validate_name(stored_filename)
    staging_path.replace(destination)
    return destination
