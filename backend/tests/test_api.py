def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_groups_list_and_search(client):
    r = client.get("/api/groups", params={"q": "fancy bear"})
    assert r.status_code == 200
    names = [g["name"] for g in r.json()["items"]]
    assert names == ["APT28"]
    apt28 = r.json()["items"][0]
    assert apt28["attribution"]["country"]["code"] == "RU"
    assert apt28["attribution"]["confidence"] == "confirmed"

    ru = client.get("/api/groups", params={"country": "RU"}).json()
    assert ru["total"] > 10


def test_group_detail(client):
    d = client.get("/api/groups/sandworm-team").json()
    assert d["attack_id"] == "G0034"
    assert any("74455" in (l["agency"] or "") for l in d["state_links"])
    titles = [h["title"] for h in d["history"]]
    assert "NotPetya" in titles
    assert "2016 Ukraine Electric Power Attack" in titles  # MITRE campaign
    assert any(r["group"]["name"] == "APT28" for r in d["relations"])
    assert d["technique_count"] > 20
    assert client.get("/api/groups/nope").status_code == 404


def test_favourites_require_login(client):
    client.cookies.clear()
    assert client.get("/api/groups", params={"scope": "favourites"}).status_code == 401
    assert client.put("/api/favourites/apt28").status_code == 401


def test_favourites_flow_and_scope(user_client):
    c = user_client
    assert c.put("/api/favourites/apt28").status_code == 204
    assert c.put("/api/favourites/apt28").status_code == 204  # idempotent
    assert c.put("/api/favourites/kimsuky").status_code == 204
    favs = c.get("/api/favourites").json()
    assert {f["slug"] for f in favs} == {"apt28", "kimsuky"}

    scoped = c.get("/api/groups", params={"scope": "favourites"}).json()
    assert {g["slug"] for g in scoped["items"]} == {"apt28", "kimsuky"}
    assert all(g["is_favourite"] for g in scoped["items"])

    g = c.get("/api/graph", params={"scope": "favourites"}).json()
    ids = {n["id"] for n in g["nodes"]}
    assert "g:apt28" in ids and "s:RU" in ids and "s:KP" in ids
    # Sandworm is pulled in as context via the same-agency relation
    ctx_nodes = {n["id"] for n in g["nodes"] if n.get("context")}
    assert "g:sandworm-team" in ctx_nodes

    assert c.delete("/api/favourites/kimsuky").status_code == 204
    assert {f["slug"] for f in c.get("/api/favourites").json()} == {"apt28"}


def test_auth_errors(client):
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"email": "x@example.org", "password": "short", "display_name": "x"})
    assert r.status_code == 422
    r = client.post("/api/auth/login", json={"email": "nobody@example.org", "password": "whatever-123"})
    assert r.status_code == 401
    assert client.get("/api/auth/me").json()["user"] is None


def test_csrf_header_required(client):
    r = client.put("/api/favourites/apt28", headers={"X-Requested-With": ""})
    assert r.status_code == 403


def test_graph_all(client):
    g = client.get("/api/graph").json()
    group_nodes = [n for n in g["nodes"] if n["type"] == "group"]
    assert len(group_nodes) > 60
    assert any(e["type"] == "relation" for e in g["edges"])
    conf = client.get("/api/graph", params={"min_confidence": "confirmed"}).json()
    assert all(e.get("confidence") == "confirmed" for e in conf["edges"] if e["type"] == "attribution")


def test_hybrid_conflicts(client):
    cs = client.get("/api/hybrid/conflicts").json()
    slugs = {c["slug"] for c in cs}
    assert {"russia-ukraine-war", "russia-georgia-2008", "israel-iran-2025"} <= slugs
    d = client.get("/api/hybrid/conflicts/israel-iran-2025").json()
    assert any(l["method"] == "curated" for l in d["links"])
    assert len(d["series"]) > 10
    assert len(d["lag_correlation"]) >= 7
    names = {p["name"] for p in d["participants"]}
    assert "Predatory Sparrow" in names


def test_sources(client):
    s = client.get("/api/sources").json()
    assert s["counts"]["groups"] > 150
    assert s["keys"] == {"otx": False, "acled": False}


def test_activity_pagination_and_country_filter(client, db):
    from datetime import datetime, timedelta, timezone

    from app.models import ActivityEvent

    now = datetime.now(timezone.utc)
    for i in range(7):
        db.add(ActivityEvent(source_key="pag", source_type="rss", source_name="Pag", external_id=f"p{i}",
                             title=f"Pagination item {i}", published_at=now - timedelta(hours=i),
                             countries=["EE"] if i % 2 == 0 else ["LV"]))
    db.commit()
    r = client.get("/api/activity", params={"q": "pagination item", "limit": 3, "offset": 0}).json()
    assert r["total"] == 7 and [x["title"] for x in r["items"]] == ["Pagination item 0", "Pagination item 1", "Pagination item 2"]
    r2 = client.get("/api/activity", params={"q": "pagination item", "limit": 3, "offset": 6}).json()
    assert [x["title"] for x in r2["items"]] == ["Pagination item 6"]
    ee = client.get("/api/activity", params={"q": "pagination item", "country": "ee"}).json()
    assert ee["total"] == 4
    assert client.get("/api/activity", params={"country": "E1"}).status_code == 422


def test_password_change_revokes_other_sessions(client):
    import uuid

    from fastapi.testclient import TestClient

    from app.main import app

    email = f"pw-{uuid.uuid4().hex[:8]}@example.org"
    client.cookies.clear()
    assert client.post("/api/auth/register", json={"email": email, "password": "first password 123", "display_name": "P"}).status_code == 201
    with TestClient(app) as other:
        other.headers.update({"X-Requested-With": "shadowtrace"})
        assert other.post("/api/auth/login", json={"email": email, "password": "first password 123"}).status_code == 200
        assert other.get("/api/auth/me").json()["user"]["email"] == email

        import time
        time.sleep(1.1)  # iat has 1 s resolution
        bad = client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "second password 456"})
        assert bad.status_code == 403
        ok = client.post("/api/auth/password", json={"current_password": "first password 123", "new_password": "second password 456"})
        assert ok.status_code == 204
        assert client.get("/api/auth/me").json()["user"]["email"] == email  # this session survives
        assert other.get("/api/auth/me").json()["user"] is None  # the other one is revoked
    assert client.post("/api/auth/login", json={"email": email, "password": "second password 456"}).status_code == 200


def test_delete_account_requires_password(user_client):
    c = user_client
    assert c.post("/api/auth/delete-account", json={"password": "nope"}).status_code == 403
    assert c.post("/api/auth/delete-account", json={"password": "correct horse battery"}).status_code == 204
    assert c.get("/api/auth/me").json()["user"] is None


def test_me_reports_registration(client):
    assert client.get("/api/auth/me").json()["registration_open"] is True


def test_runtime_settings_check(monkeypatch):
    import pytest

    from app.config import check_runtime_settings, get_settings

    monkeypatch.setenv("ST_SECRET_KEY", "change-me")
    monkeypatch.setenv("ST_DEBUG", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            check_runtime_settings()
        monkeypatch.setenv("ST_DEBUG", "true")
        get_settings.cache_clear()
        check_runtime_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_auth_rate_limit(client):
    codes = [client.post("/api/auth/login", json={"email": "rl@example.org", "password": "x"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
