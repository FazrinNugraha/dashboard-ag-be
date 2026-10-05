"""Unit test app/core/retry.py."""
import asyncio

import pytest
import requests

from app.core.retry import call_with_retry, is_retryable


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeAPIError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = FakeResponse(status_code)


class TestIsRetryable:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_status_transient(self, status):
        assert is_retryable(FakeAPIError(status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
    def test_status_tidak_diulang(self, status):
        assert is_retryable(FakeAPIError(status)) is False

    def test_error_jaringan_diulang(self):
        assert is_retryable(requests.exceptions.ConnectionError()) is True
        assert is_retryable(asyncio.TimeoutError()) is True

    def test_network_bisa_dimatikan(self):
        assert is_retryable(requests.exceptions.ConnectionError(), retry_network=False) is False

    def test_status_dibatasi_himpunan_khusus(self):
        # 500 tidak termasuk himpunan tulis -> tidak diulang (berisiko dobel)
        assert is_retryable(FakeAPIError(500), retry_statuses={429, 503}, retry_network=False) is False
        assert is_retryable(FakeAPIError(429), retry_statuses={429, 503}, retry_network=False) is True


class TestCallWithRetry:
    def test_berhasil_tanpa_retry(self):
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            return "ok"

        assert asyncio.run(call_with_retry(factory, base_delay=0)) == "ok"
        assert calls["n"] == 1

    def test_retry_lalu_berhasil(self):
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            if calls["n"] < 3:
                raise FakeAPIError(503)
            return "ok"

        assert asyncio.run(call_with_retry(factory, base_delay=0)) == "ok"
        assert calls["n"] == 3

    def test_menyerah_setelah_attempts(self):
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            raise FakeAPIError(503)

        with pytest.raises(FakeAPIError):
            asyncio.run(call_with_retry(factory, attempts=3, base_delay=0))
        assert calls["n"] == 3

    def test_error_non_transient_langsung_raise(self):
        calls = {"n": 0}

        async def factory():
            calls["n"] += 1
            raise FakeAPIError(404)

        with pytest.raises(FakeAPIError):
            asyncio.run(call_with_retry(factory, base_delay=0))
        assert calls["n"] == 1

    def test_mode_tulis_tidak_retry_500_dan_network(self):
        calls = {"n": 0}

        async def factory_500():
            calls["n"] += 1
            raise FakeAPIError(500)

        with pytest.raises(FakeAPIError):
            asyncio.run(
                call_with_retry(factory_500, base_delay=0, retry_statuses={429, 503}, retry_network=False)
            )
        assert calls["n"] == 1

        calls["n"] = 0

        async def factory_429():
            calls["n"] += 1
            raise FakeAPIError(429)

        with pytest.raises(FakeAPIError):
            asyncio.run(
                call_with_retry(factory_429, attempts=2, base_delay=0, retry_statuses={429, 503}, retry_network=False)
            )
        assert calls["n"] == 2