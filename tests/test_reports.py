"""Test validasi parameter GET /reports/export (tanpa menyentuh Sheets)."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import API  # noqa: E402


@pytest.mark.parametrize(
    "params",
    [
        {"period": "week", "value": "2026-10", "format": "xlsx"},
        {"period": "month", "value": "salah", "format": "xlsx"},
        {"period": "year", "value": "2026-10", "format": "xlsx"},
        {"period": "month", "value": "2026-10", "format": "csv"},
    ],
)
def test_export_parameter_tidak_valid_422(auth_client, params):
    r = auth_client.get(f"{API}/reports/export", params=params)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_export_tanpa_login_401(client):
    r = client.get(f"{API}/reports/export", params={"period": "month", "value": "2026-10", "format": "xlsx"})
    assert r.status_code == 401