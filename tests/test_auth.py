from tests.conftest import API, CSRF


def test_health_publik(client):
    response = client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "X-Request-ID" in response.headers


def test_me_tanpa_login_401(client):
    response = client.get(f"{API}/auth/me")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "AUTH_REQUIRED", "message": "Silakan login terlebih dahulu."}
    }


def test_login_berhasil_set_cookie_dan_me(client):
    response = client.post(
        f"{API}/auth/login",
        json={"username": "admin2", "password": "pass-admin-2"},
        headers=CSRF,
    )
    assert response.status_code == 200
    assert response.json() == {"username": "admin2"}
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    me = client.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json() == {"username": "admin2"}


def test_login_password_salah(client):
    response = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "salah"},
        headers=CSRF,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_login_username_tidak_ada_pesan_sama(client):
    response = client.post(
        f"{API}/auth/login",
        json={"username": "hantu", "password": "apa-saja"},
        headers=CSRF,
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Username atau kata sandi salah."


def test_login_tanpa_header_csrf_ditolak(client):
    response = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "pass-admin-1"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_login_payload_tidak_valid_422(client):
    response = client.post(f"{API}/auth/login", json={"username": "admin1"}, headers=CSRF)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rate_limit_percobaan_keenam(client):
    for _ in range(5):
        response = client.post(
            f"{API}/auth/login",
            json={"username": "admin1", "password": "salah"},
            headers=CSRF,
        )
        assert response.status_code == 401

    blocked = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "salah"},
        headers=CSRF,
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"

    # Kata sandi benar pun tetap diblokir selama jendela belum habis
    still_blocked = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "pass-admin-1"},
        headers=CSRF,
    )
    assert still_blocked.status_code == 429


def test_login_sukses_mereset_hitungan(client):
    for _ in range(4):
        client.post(
            f"{API}/auth/login",
            json={"username": "admin1", "password": "salah"},
            headers=CSRF,
        )
    ok = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "pass-admin-1"},
        headers=CSRF,
    )
    assert ok.status_code == 200
    wrong = client.post(
        f"{API}/auth/login",
        json={"username": "admin1", "password": "salah"},
        headers=CSRF,
    )
    assert wrong.status_code == 401  # bukan 429


def test_logout_menghapus_sesi(auth_client):
    assert auth_client.get(f"{API}/auth/me").status_code == 200
    response = auth_client.post(f"{API}/auth/logout", headers=CSRF)
    assert response.status_code == 204
    assert auth_client.get(f"{API}/auth/me").status_code == 401


def test_route_tidak_ada_format_error_seragam(client):
    response = client.get(f"{API}/tidak-ada")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
