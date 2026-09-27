def test_redirect_follows_to_original_url(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/target"}).json()
    resp = client.get(f"/{created['code']}", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/target"


def test_redirect_increments_click_count(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/counted"}).json()
    code = created["code"]

    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)

    detail = client.get(f"/api/v1/urls/{code}").json()
    assert detail["click_count"] == 3


def test_redirect_missing_code_returns_404(client):
    resp = client.get("/does-not-exist-xyz", follow_redirects=False)
    assert resp.status_code == 404


def test_redirect_deleted_url_returns_410(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/gone"}).json()
    code = created["code"]
    client.delete(f"/api/v1/urls/{code}")
    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 410
    assert resp.json()["error"] == "url_gone"


def test_redirect_expired_url_returns_410(client, monkeypatch):
    import app.crud as crud_module

    created = client.post(
        "/api/v1/urls", json={"original_url": "https://example.com/expired", "expires_in_days": 1}
    ).json()
    code = created["code"]

    # Force "now" far enough in the future that the 1-day expiry has passed.
    from datetime import timedelta

    real_utcnow = crud_module._utcnow

    def fake_future_now():
        return real_utcnow() + timedelta(days=2)

    import app.models as models_module

    monkeypatch.setattr(models_module, "_utcnow", fake_future_now)

    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 410
