import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.idempotency import IdempotencyMiddleware

logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    is_production = settings.ENV == "production"

    app = FastAPI(
        title="Dashboard Keuangan AGUNGJAYA ALUMINIUM API",
        version=__version__,
        openapi_url=None if is_production else f"{settings.API_PREFIX}/openapi.json",
        docs_url=None if is_production else "/docs",
        redoc_url=None,
    )

    # Urutan add_middleware: yang ditambahkan terakhir paling luar. CORS harus
    # paling luar agar respons replay idempotency tetap mendapat header CORS.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With", "Idempotency-Key"],
        expose_headers=["Idempotency-Replayed"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info("%s %s -> %s [%s]", request.method, request.url.path, response.status_code, request_id)
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.API_PREFIX)
    return app


app = create_app()