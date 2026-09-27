import pytest


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "ftp://example.com/file",
        "not-a-url",
        "http://localhost/internal",
        "http://127.0.0.1/admin",
        "http://192.168.1.1/router",
    ],
)
def test_invalid_or_unsafe_urls_rejected(client, bad_url):
    resp = client.post("/api/v1/urls", json={"original_url": bad_url})
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_url"


def test_blocklisted_domain_rejected(client, tmp_path, monkeypatch):
    from app import security

    blocklist_file = tmp_path / "blocklist.txt"
    blocklist_file.write_text("evil-example.test\n")
    monkeypatch.setattr(security.settings, "blocklist_path", str(blocklist_file))
    security.reload_blocklist_for_tests()
    try:
        resp = client.post("/api/v1/urls", json={"original_url": "https://evil-example.test/phish"})
        assert resp.status_code == 422
    finally:
        security.reload_blocklist_for_tests.__globals__["_BLOCKLIST"] = set()


def test_alias_with_invalid_characters_rejected_by_schema(client):
    resp = client.post(
        "/api/v1/urls",
        json={"original_url": "https://example.com/a", "custom_alias": "bad alias!"},
    )
    assert resp.status_code == 422


def test_blank_url_rejected(client):
    resp = client.post("/api/v1/urls", json={"original_url": "   "})
    assert resp.status_code == 422
