"""Error 500 harus tetap membawa header CORS.

Regresi ini penting: exception tak terduga ditangani di luar CORSMiddleware,
sehingga tanpa header CORS browser menampilkan "Failed to fetch" dan menyembunyikan
pesan error sebenarnya.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers

ALLOWED_ORIGIN = "http://localhost:5173"
DENIED_ORIGIN = "http://evil.example.com"


def _boom_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    return app


def test_500_has_cors_headers_for_allowed_origin():
    client = TestClient(_boom_app(), raise_server_exceptions=False)
    res = client.get("/boom", headers={"Origin": ALLOWED_ORIGIN})
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert res.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_500_omits_cors_headers_for_denied_origin():
    client = TestClient(_boom_app(), raise_server_exceptions=False)
    res = client.get("/boom", headers={"Origin": DENIED_ORIGIN})
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") is None


def test_500_without_origin_has_no_cors_headers():
    client = TestClient(_boom_app(), raise_server_exceptions=False)
    res = client.get("/boom")
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") is None