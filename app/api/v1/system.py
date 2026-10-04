from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["System"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check (publik)."""
    return {"status": "ok", "version": __version__, "env": get_settings().ENV}
