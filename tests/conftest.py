import os

import bcrypt

# Environment HARUS di-set sebelum app diimpor (Settings dibaca saat import).
def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


os.environ.update(
    {
        "ENV": "test",
        "JWT_SECRET": "test-secret-test-secret-test-secret-123456",
        "COOKIE_SECURE": "false",
        "CORS_ORIGINS": "http://localhost:5173",
        "ADMIN1_USERNAME": "admin1",
        "ADMIN1_PASSWORD_HASH": _hash("pass-admin-1"),
        "ADMIN2_USERNAME": "admin2",
        "ADMIN2_PASSWORD_HASH": _hash("pass-admin-2"),
        "MAX_UPLOAD_MB": "1",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.rate_limit import login_limiter  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
CSRF = {"X-Requested-With": "test"}


@pytest.fixture(autouse=True)
def _reset_limiter():
    login_limiter.clear()
    yield
    login_limiter.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client):
    response = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "pass-admin-1"},
        headers=CSRF,
    )
    assert response.status_code == 200, response.text
    return client
