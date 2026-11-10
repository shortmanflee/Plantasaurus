import httpx
import respx

from tests.conftest import png_bytes

OPB = "https://open.plantbook.io/api/v1"
DETAIL = {
    "pid": "monstera deliciosa",
    "display_pid": "Monstera deliciosa",
    "alias": "swiss cheese plant",
    "category": "Araceae",
    "max_light_mmol": 2500,
    "min_light_mmol": 1200,
    "max_light_lux": 30000,
    "min_light_lux": 1500,
    "max_temp": 32,
    "min_temp": 12,
    "max_env_humid": 80,
    "min_env_humid": 30,
    "max_soil_moist": 60,
    "min_soil_moist": 15,
    "max_soil_ec": 2000,
    "min_soil_ec": 350,
    "image_url": "https://img.example.com/monstera.jpg",
}


def _mock_opb(mock):
    mock.post(f"{OPB}/token/").mock(return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600}))
    mock.get(f"{OPB}/plant/search").mock(
        return_value=httpx.Response(200, json={"count": 1, "results": [{k: DETAIL[k] for k in ("pid", "display_pid", "alias", "category")}]})
    )
    mock.get(f"{OPB}/plant/detail/monstera%20deliciosa/").mock(return_value=httpx.Response(200, json=DETAIL))
    mock.get(DETAIL["image_url"]).mock(return_value=httpx.Response(200, content=png_bytes()))


def test_plant_crud(client):
    p = client.post("/api/v1/plants", json={"common_name": "Lavender", "category": "Lamiaceae", "toxic_to_pets": True}).json()
    assert client.get("/api/v1/plants", params={"q": "lav"}).json()["total"] == 1
    assert client.get("/api/v1/plants/categories").json() == ["Lamiaceae"]
    assert client.patch(f"/api/v1/plants/{p['id']}", json={"notes": "smells nice"}).json()["notes"] == "smells nice"
    assert client.patch(f"/api/v1/plants/{p['id']}", json={"common_name": ""}).status_code == 422
    assert client.delete(f"/api/v1/plants/{p['id']}").status_code == 204
    assert client.get(f"/api/v1/plants/{p['id']}").status_code == 404


def test_opb_search_and_import(client):
    with respx.mock(assert_all_called=False) as mock:
        _mock_opb(mock)
        results = client.get("/api/v1/openplantbook/search", params={"q": "monstera"}).json()
        assert results[0]["pid"] == "monstera deliciosa" and results[0]["already_imported_plant_id"] is None

        r = client.post("/api/v1/plants/import-opb", json={"pid": "monstera deliciosa"})
        assert r.status_code == 201, r.text
        plant = r.json()
        assert plant["common_name"] == "Swiss Cheese Plant"
        assert plant["scientific_name"] == "Monstera deliciosa"
        assert plant["min_temp"] == 12 and plant["max_soil_ec"] == 2000
        assert plant["image_media_id"] is not None

        img = client.get(f"/api/v1/media/{plant['image_media_id']}/thumb")
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

        again = client.get("/api/v1/openplantbook/search", params={"q": "monstera"}).json()
        assert again[0]["already_imported_plant_id"] == plant["id"]
        assert client.post("/api/v1/plants/import-opb", json={"pid": "monstera deliciosa"}).status_code == 409

        client.patch(f"/api/v1/plants/{plant['id']}", json={"min_temp": 5})
        refreshed = client.post(f"/api/v1/plants/{plant['id']}/opb-refresh").json()
        assert refreshed["min_temp"] == 12 and refreshed["common_name"] == "Swiss Cheese Plant"


def _unset_env_credentials(monkeypatch):
    from app import config

    monkeypatch.delenv("PLANTASAURUS_OPB_CLIENT_ID")
    monkeypatch.delenv("PLANTASAURUS_OPB_CLIENT_SECRET")
    config.get_settings.cache_clear()


def test_opb_not_configured(client, monkeypatch):
    _unset_env_credentials(monkeypatch)
    assert client.get("/api/v1/openplantbook/status").json() == {"configured": False, "source": None, "client_id": None}
    assert client.get("/api/v1/openplantbook/search", params={"q": "rose"}).status_code == 503


def test_opb_environment_credentials(client):
    status = client.get("/api/v1/openplantbook/status").json()
    assert status == {"configured": True, "source": "environment", "client_id": "cid"}


def test_opb_config_from_ui(client, monkeypatch):
    _unset_env_credentials(monkeypatch)
    seen = []

    def token(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        seen.append(form["client_id"])
        if form["client_secret"] != "good":
            return httpx.Response(401, json={"error": "invalid_client"})
        return httpx.Response(200, json={"access_token": f"tok-{form['client_id']}", "expires_in": 3600})

    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{OPB}/token/").mock(side_effect=token)
        search = mock.get(f"{OPB}/plant/search").mock(return_value=httpx.Response(200, json={"results": []}))

        # bad credentials are tested and not saved
        r = client.put("/api/v1/openplantbook/config", json={"client_id": "me", "client_secret": "bad"})
        assert r.status_code == 502 and "rejected" in r.json()["detail"]
        assert client.get("/api/v1/openplantbook/status").json()["configured"] is False
        assert client.put("/api/v1/openplantbook/config", json={"client_id": "me"}).status_code == 422

        r = client.put("/api/v1/openplantbook/config", json={"client_id": "me", "client_secret": "good"})
        assert r.status_code == 200 and r.json() == {"configured": True, "source": "settings", "client_id": "me"}
        client.get("/api/v1/openplantbook/search", params={"q": "rose"})
        assert search.calls.last.request.headers["Authorization"] == "Bearer tok-me"

        # secret is kept when omitted for the same client id, but required for a new one
        assert client.put("/api/v1/openplantbook/config", json={"client_id": "me"}).status_code == 200
        assert client.put("/api/v1/openplantbook/config", json={"client_id": "you"}).status_code == 422

        # switching credentials drops the cached token
        client.put("/api/v1/openplantbook/config", json={"client_id": "you", "client_secret": "good"})
        client.get("/api/v1/openplantbook/search", params={"q": "fern"})
        assert search.calls.last.request.headers["Authorization"] == "Bearer tok-you"

        # UI settings take precedence over the environment, and clearing falls back to it
        monkeypatch.setenv("PLANTASAURUS_OPB_CLIENT_ID", "cid")
        monkeypatch.setenv("PLANTASAURUS_OPB_CLIENT_SECRET", "csecret")
        from app import config

        config.get_settings.cache_clear()
        assert client.get("/api/v1/openplantbook/status").json()["source"] == "settings"
        r = client.put("/api/v1/openplantbook/config", json={"client_id": None})
        assert r.json() == {"configured": True, "source": "environment", "client_id": "cid"}


def test_opb_config_requires_admin(client):
    client.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    assert client.get("/api/v1/openplantbook/status").status_code == 200
    assert client.put("/api/v1/openplantbook/config", json={"client_id": None}).status_code == 403


def test_media_upload_and_photo_event(client, garden):
    inst = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"], "spot_id": garden["bed"]["id"]}).json()
    r = client.post(
        "/api/v1/media",
        files={"file": ("leaf.png", png_bytes(), "image/png")},
        data={"instance_id": str(inst["id"]), "caption": "new leaf", "log_photo_event": "true"},
    )
    assert r.status_code == 201, r.text
    media = r.json()
    assert media["width"] == 32 and media["event_id"] is not None
    assert client.get(f"/api/v1/media/{media['id']}/file").content == png_bytes()
    tl = client.get(f"/api/v1/instances/{inst['id']}/timeline").json()
    assert tl[0]["event"]["event_type"] == "photo" and tl[0]["media"][0]["id"] == media["id"]

    bad = client.post("/api/v1/media", files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422

    client.patch(f"/api/v1/plants/{garden['plant']['id']}", json={"image_media_id": media["id"]})
    assert client.delete(f"/api/v1/media/{media['id']}").status_code == 204
    assert client.get(f"/api/v1/plants/{garden['plant']['id']}").json()["image_media_id"] is None


def test_spa_ingress_injection(settings, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings.static_dir = dist
    c = TestClient(create_app(settings))
    html = c.get("/plants/3", headers={"X-Ingress-Path": "/api/hassio_ingress/abc"}).text
    assert '<base href="/api/hassio_ingress/abc/">' in html
    assert 'window.__BASE_PATH__="/api/hassio_ingress/abc/"' in html
    assert '<base href="/">' in c.get("/").text
    assert '<base href="/">' in c.get("/", headers={"X-Ingress-Path": '"><script>'}).text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/v1/nope").status_code == 404
    assert c.get("/api/v1/nope").headers["content-type"] == "application/json"
