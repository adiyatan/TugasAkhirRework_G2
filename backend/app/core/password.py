import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    """Hash password menggunakan PBKDF2-HMAC-SHA256 dengan random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Memverifikasi password terhadap hash tersimpan."""
    try:
        salt, expected_digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    actual_digest = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return hmac.compare_digest(actual_digest, expected_digest)
