def test_setup_only_once(anon):
    assert anon.get("/api/v1/auth/status").json()["setup_required"] is True
    r = anon.post("/api/v1/auth/setup", json={"username": "admin", "password": "password123"})
    assert r.status_code == 201
    assert anon.get("/api/v1/auth/me").json()["username"] == "admin"
    r = anon.post("/api/v1/auth/setup", json={"username": "evil", "password": "password123"})
    assert r.status_code == 409


def test_requires_auth(anon):
    assert anon.get("/api/v1/plants").status_code == 401


def test_login_logout(client):
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/plants").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "password123"}).status_code == 200
    assert client.get("/api/v1/plants").status_code == 200


def test_password_change_invalidates_sessions(client, anon):
    from fastapi.testclient import TestClient

    other = TestClient(client.app)
    assert other.post("/api/v1/auth/login", json={"username": "admin", "password": "password123"}).status_code == 200
    me = client.get("/api/v1/auth/me").json()
    client.patch(f"/api/v1/users/{me['id']}", json={"password": "newpassword1"})
    assert other.get("/api/v1/plants").status_code == 401


def test_api_tokens(client):
    from fastapi.testclient import TestClient

    created = client.post("/api/v1/tokens", json={"name": "home assistant"}).json()
    token = created["token"]
    assert token.startswith("pts_")
    bare = TestClient(client.app)
    assert bare.get("/api/v1/plants").status_code == 401
    assert bare.get("/api/v1/plants", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert bare.get("/api/v1/plants", headers={"Authorization": "Bearer pts_nope"}).status_code == 401
    listed = client.get("/api/v1/tokens").json()
    assert "token" not in listed[0] and listed[0]["last_used_at"] is not None
    client.delete(f"/api/v1/tokens/{created['id']}")
    assert bare.get("/api/v1/plants", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_non_admin_restrictions(client):
    from fastapi.testclient import TestClient

    client.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    bob = TestClient(client.app)
    bob.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    assert bob.post("/api/v1/users", json={"username": "eve", "password": "password123"}).status_code == 403
    assert bob.get("/api/v1/plants").status_code == 200
    admin_id = client.get("/api/v1/auth/me").json()["id"]
    assert bob.patch(f"/api/v1/users/{admin_id}", json={"display_name": "x"}).status_code == 403


def test_ingress_headers(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("PLANTASAURUS_INGRESS_MODE", "true")
    monkeypatch.setenv("PLANTASAURUS_INGRESS_TRUSTED_IPS", '["testclient"]')
    get_settings.cache_clear()
    c = TestClient(create_app(get_settings()))
    headers = {"X-Remote-User-Id": "abc123def456", "X-Remote-User-Name": "mike"}
    r = c.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == "mike" and r.json()["is_admin"] is True
    # not trusted without header
    assert c.get("/api/v1/auth/me").status_code == 401
