"""Test Idempotency-Key memakai app FastAPI terisolasi (tanpa Sheets)."""
import threading

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.idempotency import IdempotencyMiddleware, IdempotencyStore

CALLS = {"n": 0}
LOCK = threading.Lock()


def build_app():
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        with LOCK:
            CALLS["n"] += 1
        return {"count": CALLS["n"]}

    @app.post("/boom")
    async def boom():
        raise RuntimeError("gagal sementara")

    @app.get("/read")
    async def read():
        with LOCK:
            CALLS["n"] += 1
        return {"count": CALLS["n"]}

    return app


@pytest.fixture(autouse=True)
def _reset():
    CALLS["n"] = 0
    yield
    CALLS["n"] = 0


@pytest.fixture
def client():
    with TestClient(build_app(), raise_server_exceptions=False) as c:
        yield c


def test_tanpa_key_dijalankan_dua_kali(client):
    a = client.post("/echo")
    b = client.post("/echo")
    assert a.json() == {"count": 1}
    assert b.json() == {"count": 2}


def test_key_sama_replay(client):
    a = client.post("/echo", headers={"Idempotency-Key": "abc"})
    b = client.post("/echo", headers={"Idempotency-Key": "abc"})
    assert a.json() == {"count": 1}
    assert b.json() == {"count": 1}  # tidak mengeksekusi handler lagi
    assert b.headers.get("Idempotency-Replayed") == "true"


def test_key_berbeda_eksekusi_terpisah(client):
    client.post("/echo", headers={"Idempotency-Key": "a"})
    b = client.post("/echo", headers={"Idempotency-Key": "b"})
    assert b.json() == {"count": 2}


def test_get_diabaikan(client):
    client.get("/read", headers={"Idempotency-Key": "x"})
    b = client.get("/read", headers={"Idempotency-Key": "x"})
    assert b.json() == {"count": 2}


def test_5xx_tidak_disimpan(client):
    # 500 bersifat sementara -> tidak boleh di-replay agar bisa dicoba ulang.
    a = client.post("/boom", headers={"Idempotency-Key": "z"})
    b = client.post("/boom", headers={"Idempotency-Key": "z"})
    assert a.status_code == 500 and b.status_code == 500
    assert "idempotency-replayed" not in {k.lower() for k in b.headers}


class TestStore:
    def test_prune_kadaluarsa(self):
        store = IdempotencyStore(ttl_seconds=0)
        from app.core.idempotency import _Entry
        import time as _time

        store.put("k", _Entry(200, b"{}", "application/json", {}, _time.monotonic() - 1))
        assert store.get("k") is None

    def test_clear(self):
        from app.core.idempotency import _Entry
        import time as _time

        store = IdempotencyStore()
        store.put("k", _Entry(200, b"{}", "application/json", {}, _time.monotonic()))
        store.clear()
        assert store.get("k") is None