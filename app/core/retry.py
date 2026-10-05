"""Retry dengan exponential backoff + jitter untuk panggilan Google API.

Hanya error transien (rate limit / 5xx / masalah jaringan) yang diulang;
error lain (mis. 404, 403) langsung diteruskan agar tidak menyembunyikan bug.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0
DEFAULT_JITTER = 0.3


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def is_retryable(
    exc: Exception,
    retry_statuses: set[int] = RETRYABLE_STATUS,
    retry_network: bool = True,
) -> bool:
    """True bila exception layak dicoba ulang."""
    status = _status_code(exc)
    if status is not None:
        return status in retry_statuses
    if not retry_network:
        return False
    # Kesalahan jaringan/transport (timeout, koneksi putus) juga transien.
    return isinstance(exc, (requests.exceptions.RequestException, asyncio.TimeoutError))


async def call_with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    retry_statuses: set[int] = RETRYABLE_STATUS,
    retry_network: bool = True,
) -> T:
    """Panggil `factory()` berulang dengan backoff. `factory` harus membuat
    coroutine baru tiap pemanggilan agar aman di-await lebih dari sekali.

    Catatan operasi tulis: append TIDAK idempotent. Untuk penulisan, panggil
    dengan `retry_statuses={429, 503}` dan `retry_network=False` karena 429/503
    berarti permintaan belum diproses, sedangkan timeout/5xx lain bisa saja
    sudah dieksekusi sehingga retry berisiko menggandakan baris.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - dipilah oleh is_retryable
            last_exc = exc
            if attempt >= attempts or not is_retryable(exc, retry_statuses, retry_network):
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, jitter)
            logger.warning(
                "Google API error (attempt %d/%d), retry dalam %.2fs: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Tidak tercapai (loop selalu raise/return), jaga-jaga untuk type checker.
    assert last_exc is not None
    raise last_exc