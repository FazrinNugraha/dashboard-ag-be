from fastapi import APIRouter, Depends, Request, Response

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import login_limiter
from app.core.security import (
    create_access_token,
    dummy_hash,
    get_current_admin,
    verify_password,
)
from app.schemas.auth import AdminOut, LoginRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_ip(request: Request) -> str:
    # Di belakang reverse proxy, atur proxy agar meneruskan IP asli (mis. uvicorn --proxy-headers).
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=AdminOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AdminOut:
    key = f"login:{_client_ip(request)}"
    login_limiter.check(key)

    stored_hash = settings.admins.get(payload.username)
    # Selalu jalankan bcrypt agar waktu respons tidak membocorkan keberadaan username.
    valid = verify_password(payload.password, stored_hash or dummy_hash())
    if not stored_hash or not valid:
        login_limiter.hit(key)
        raise AppError("AUTH_INVALID", "Username atau kata sandi salah.", 401)

    login_limiter.reset(key)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=create_access_token(payload.username, settings),
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return AdminOut(username=payload.username)


@router.post("/logout", status_code=204)
def logout(settings: Settings = Depends(get_settings)) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return response


@router.get("/me", response_model=AdminOut)
def me(username: str = Depends(get_current_admin)) -> AdminOut:
    return AdminOut(username=username)
