"""Hash kata sandi (bcrypt), sesi JWT, dan dependency autentikasi."""
import functools
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import AppError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_BCRYPT_MAX_BYTES = 72  # batas bawaan bcrypt


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except ValueError:
        return False


@functools.cache
def dummy_hash() -> str:
    """Hash palsu agar waktu verifikasi sama untuk username yang tidak ada."""
    return hash_password("dummy-password-for-timing")


def create_access_token(username: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def get_current_admin(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """Kembalikan username admin dari cookie sesi, atau 401."""
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise AppError("AUTH_REQUIRED", "Silakan login terlebih dahulu.", 401)
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise AppError("AUTH_INVALID", "Sesi tidak valid atau sudah berakhir.", 401)
    username = payload.get("sub")
    if not username or username not in settings.admins:
        raise AppError("AUTH_INVALID", "Sesi tidak valid atau sudah berakhir.", 401)
    return username


def csrf_protect(request: Request) -> None:
    """Request mutasi wajib membawa header kustom (tidak bisa dikirim form lintas-situs)."""
    if request.method not in SAFE_METHODS and not request.headers.get("x-requested-with"):
        raise AppError(
            "CSRF_FAILED",
            "Header X-Requested-With wajib untuk request mutasi.",
            403,
        )
