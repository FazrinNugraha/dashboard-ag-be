"""Validasi batas paginasi (gagal sebelum menyentuh Sheets)."""
import pytest

from tests.conftest import API


@pytest.mark.parametrize("query", ["page=0", "page=-1", "page_size=0", "page_size=101"])
def test_paginasi_tidak_valid_422(auth_client, query):
    r = auth_client.get(f"{API}/projects?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("query", ["page=0", "page_size=999"])
def test_paginasi_expenses_tidak_valid_422(auth_client, query):
    r = auth_client.get(f"{API}/expenses?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"