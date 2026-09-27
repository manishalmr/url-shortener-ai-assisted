def test_analytics_reports_total_and_referrers(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/analytics"}).json()
    code = created["code"]

    client.get(f"/{code}", follow_redirects=False, headers={"referer": "https://google.com"})
    client.get(f"/{code}", follow_redirects=False, headers={"referer": "https://google.com"})
    client.get(f"/{code}", follow_redirects=False, headers={"referer": "https://twitter.com"})

    resp = client.get(f"/api/v1/urls/{code}/analytics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clicks"] == 3
    assert body["clicks_last_24h"] == 3
    assert body["last_clicked_at"] is not None
    referrer_map = {r["referrer"]: r["clicks"] for r in body["top_referrers"]}
    assert referrer_map["https://google.com"] == 2
    assert referrer_map["https://twitter.com"] == 1
    assert len(body["clicks_by_day"]) == 1


def test_analytics_for_unknown_code_returns_404(client):
    resp = client.get("/api/v1/urls/unknown/analytics")
    assert resp.status_code == 404


def test_analytics_with_zero_clicks(client):
    created = client.post("/api/v1/urls", json={"original_url": "https://example.com/noclicks"}).json()
    resp = client.get(f"/api/v1/urls/{created['code']}/analytics")
    body = resp.json()
    assert body["total_clicks"] == 0
    assert body["last_clicked_at"] is None
    assert body["clicks_by_day"] == []
