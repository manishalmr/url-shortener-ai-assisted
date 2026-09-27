from app.rate_limiter import FixedWindowRateLimiter


def test_fixed_window_rate_limiter_allows_up_to_limit():
    limiter = FixedWindowRateLimiter(limit_per_minute=3)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False


def test_fixed_window_rate_limiter_is_per_key():
    limiter = FixedWindowRateLimiter(limit_per_minute=1)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-a") is False


def test_create_endpoint_enforces_rate_limit(client, monkeypatch):
    from app.routers import urls as urls_router

    limiter_cls = type(urls_router.create_rate_limiter)
    monkeypatch.setattr(urls_router, "create_rate_limiter", limiter_cls(2))

    ok1 = client.post("/api/v1/urls", json={"original_url": "https://example.com/1"})
    ok2 = client.post("/api/v1/urls", json={"original_url": "https://example.com/2"})
    blocked = client.post("/api/v1/urls", json={"original_url": "https://example.com/3"})

    assert ok1.status_code == 201
    assert ok2.status_code == 201
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "rate_limit_exceeded"
