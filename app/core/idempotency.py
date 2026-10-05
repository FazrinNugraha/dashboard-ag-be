"""Idempotency-Key untuk request mutasi.

Mencegah efek ganda saat FE double-click / klien retry otomatis: request dengan
kunci sama mengembalikan respons yang tersimpan tanpa menjalankan ulang handler.

Sesuai prinsip 1 instance backend, store disimpan di memori (lihat PRD 6.5).
Bila kelak multi-instance, pindahkan ke Redis.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
TTL_SECONDS = 600  # 10 menit
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class _Entry:
    status_code: int
    body: bytes
    media_type: str | None
    headers: dict[str, str]
    created_at: float


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, e in self._entries.items() if now - e.created_at > self.ttl_seconds]
        for k in expired:
            self._entries.pop(k, None)
            self._locks.pop(k, None)

    def get(self, key: str) -> _Entry | None:
        self._prune()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.created_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry

    def put(self, key: str, entry: _Entry) -> None:
        self._entries[key] = entry

    def lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()


idempotency_store = IdempotencyStore()


def _scope_key(request: Request, raw_key: str) -> str:
    """Batasi kunci per sesi + method + path agar tidak bocor antar pengguna."""
    session = request.cookies.get("access_token", "")
    basis = f"{session}|{request.method}|{request.url.path}|{raw_key}"
    return hashlib.sha256(basis.encode()).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not raw_key or request.method in SAFE_METHODS:
            return await call_next(request)

        key = _scope_key(request, raw_key)

        existing = idempotency_store.get(key)
        if existing is not None:
            headers = dict(existing.headers)
            headers["Idempotency-Replayed"] = "true"
            return Response(
                content=existing.body,
                status_code=existing.status_code,
                media_type=existing.media_type,
                headers=headers,
            )

        async with idempotency_store.lock_for(key):
            # Cek ulang: request paralel dengan kunci sama menunggu di lock.
            existing = idempotency_store.get(key)
            if existing is not None:
                headers = dict(existing.headers)
                headers["Idempotency-Replayed"] = "true"
                return Response(
                    content=existing.body,
                    status_code=existing.status_code,
                    media_type=existing.media_type,
                    headers=headers,
                )

            response = await call_next(request)
            body = b"".join([chunk async for chunk in response.body_iterator])

            # Simpan hanya respons deterministik (2xx/4xx). 5xx bersifat
            # sementara sehingga klien boleh mencoba ulang.
            if response.status_code < 500:
                stored_headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"content-length", "content-type"}
                }
                idempotency_store.put(
                    key,
                    _Entry(
                        status_code=response.status_code,
                        body=body,
                        media_type=response.media_type,
                        headers=stored_headers,
                        created_at=time.monotonic(),
                    ),
                )
                logger.info("Idempotency: disimpan %s (%s)", key[:12], response.status_code)

            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=dict(response.headers),
            )