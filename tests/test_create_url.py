import pytest


def test_create_short_url_success(client):
    resp = client.post("/api/v1/urls", json={"original_url": "https://example.com/some/long/path"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["original_url"] == "https://example.com/some/long/path"
    assert len(body["code"]) == 7
    assert body["short_url"].endswith(body["code"])
    assert body["is_custom_alias"] is False


def test_create_short_url_with_custom_alias(client):
    resp = client.post(
        "/api/v1/urls",
        json={"original_url": "https://example.com/x", "custom_alias": "my-alias"},
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "my-alias"
    assert resp.json()["is_custom_alias"] is True


def test_concurrent_duplicate_alias_creation_handled_gracefully(db_session, monkeypatch):
    """Regression test for a real race condition found via a live two-thread probe:
    two concurrent requests for the same custom alias can both pass the
    `code_exists` check before either commits (check-then-act race). The DB's
    UNIQUE constraint on `code` prevents a duplicate row, but the second caller
    must get a clean AliasUnavailableError (-> 409), not a raw IntegrityError
    (-> 500). We simulate the race deterministically by forcing `code_exists`
    to always report "not taken", mimicking the race window, rather than relying
    on real thread timing (which is flaky in CI).
    """
    from app import crud
    from app.exceptions import AliasUnavailableError

    monkeypatch.setattr(crud, "code_exists", lambda db, code: False)

    crud.create_url(
        db_session,
        original_url="https://example.com/first",
        custom_alias="race-alias",
        expires_in_days=None,
        code_length=7,
        max_attempts=5,
    )

    with pytest.raises(AliasUnavailableError):
        crud.create_url(
            db_session,
            original_url="https://example.com/second",
            custom_alias="race-alias",
            expires_in_days=None,
            code_length=7,
            max_attempts=5,
        )


def test_duplicate_custom_alias_rejected(client):
    client.post(
        "/api/v1/urls", json={"original_url": "https://example.com/a", "custom_alias": "dup"}
    )
    resp = client.post(
        "/api/v1/urls", json={"original_url": "https://example.com/b", "custom_alias": "dup"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "alias_unavailable"


def test_reserved_alias_rejected(client):
    resp = client.post(
        "/api/v1/urls", json={"original_url": "https://example.com/a", "custom_alias": "health"}
    )
    assert resp.status_code == 409


def test_dedup_returns_existing_code_for_same_url(client):
    first = client.post("/api/v1/urls", json={"original_url": "https://example.com/dedup"})
    second = client.post("/api/v1/urls", json={"original_url": "https://example.com/dedup"})
    assert first.json()["code"] == second.json()["code"]


def test_expiry_in_days_sets_expires_at(client):
    resp = client.post(
        "/api/v1/urls", json={"original_url": "https://example.com/expiring", "expires_in_days": 1}
    )
    assert resp.json()["expires_at"] is not None


def test_get_and_delete_url(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/y"}).json()
    code = created["code"]

    got = client.get(f"/api/v1/urls/{code}")
    assert got.status_code == 200
    assert got.json()["click_count"] == 0

    deleted = client.delete(f"/api/v1/urls/{code}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/urls/{code}")
    assert missing.status_code == 200  # metadata endpoint still finds it (soft delete)
    assert missing.json()["is_active"] is False


def test_get_nonexistent_url_returns_404(client):
    resp = client.get("/api/v1/urls/doesnotexist")
    assert resp.status_code == 404
    assert resp.json()["error"] == "url_not_found"


def test_list_urls_pagination(client):
    for i in range(3):
        client.post("/api/v1/urls", json={"original_url": f"https://example.com/{i}"})
    resp = client.get("/api/v1/urls?limit=2&offset=0")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
