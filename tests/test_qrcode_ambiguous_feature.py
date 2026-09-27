def test_qrcode_returns_png_for_existing_code(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/qr"}).json()
    resp = client.get(f"/api/v1/urls/{created['code']}/qrcode")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


def test_qrcode_for_unknown_code_returns_404(client):
    resp = client.get("/api/v1/urls/unknown/qrcode")
    assert resp.status_code == 404
