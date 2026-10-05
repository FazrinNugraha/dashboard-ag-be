from tests.conftest import API, CSRF

URL = f"{API}/invoices/extract"


def _upload(client, content: bytes, headers=CSRF):
    return client.post(
        URL,
        files={"file": ("invoice.pdf", content, "application/pdf")},
        headers=headers,
    )


def test_extract_wajib_login(client):
    response = _upload(client, b"%PDF-1.4 dummy")
    assert response.status_code == 401


def test_extract_bukan_pdf_ditolak(auth_client):
    response = _upload(auth_client, b"ini bukan pdf")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "PDF_INVALID"


def test_extract_terlalu_besar_ditolak(auth_client):
    too_big = b"%PDF" + b"0" * (1024 * 1024)  # batas tes = 1 MB
    response = _upload(auth_client, too_big)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PDF_TOO_LARGE"


def test_extract_pdf_rusak_ditolak(auth_client):
    response = _upload(auth_client, b"%PDF-1.4 rusak total")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "PDF_INVALID"


def test_extract_tanpa_header_csrf_ditolak(auth_client):
    response = _upload(auth_client, b"%PDF-1.4 dummy", headers={})
    assert response.status_code == 403
