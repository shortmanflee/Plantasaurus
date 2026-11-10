import json

import httpx
import pytest
import respx

HA = "http://ha.test:8123"


class FakeHA:
    """Mimics the parts of HA's REST API we use: the template endpoint and notification services."""

    def __init__(self):
        self.devices = {
            "zone1": {"name": "Front Lawn Zone", "area": "Garden", "labels": {"Irrigation Zone"}},
            "zone2": {"name": "Veg Bed Zone", "area": "Garden", "labels": {"Irrigation Zone"}},
            "mon1": {"name": "Flower Care 1", "area": "Living Room", "labels": {"plant"}},
            "other": {"name": "TV", "area": "Living Room", "labels": set()},
        }
        self.notifications: dict[str, dict] = {}
        self.template_calls = 0
        self.down = False

    def template(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("boom")
        if request.headers["Authorization"] != "Bearer good-token":
            return httpx.Response(401, json={"message": "Invalid token"})
        self.template_calls += 1
        v = json.loads(request.content)["variables"]
        zones = [d for d, info in self.devices.items() if v["zone_label"] in info["labels"]]
        monitors = [d for d, info in self.devices.items() if v["monitor_label"] in info["labels"]]
        ids = dict.fromkeys(zones + monitors + v["check_ids"])
        devices = [
            {"id": d, "name": self.devices[d]["name"], "area": self.devices[d]["area"], "manufacturer": None,
             "model": None, "entities": [f"sensor.{d}_moisture"]}
            for d in ids if d in self.devices
        ]
        return httpx.Response(200, text=json.dumps({"zones": zones, "monitors": monitors, "devices": devices}))

    def create(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.notifications[body["notification_id"]] = body
        return httpx.Response(200, json=[])

    def dismiss(self, request: httpx.Request) -> httpx.Response:
        self.notifications.pop(json.loads(request.content)["notification_id"], None)
        return httpx.Response(200, json=[])


@pytest.fixture
def fake_ha():
    fake = FakeHA()
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{HA}/api/template").mock(side_effect=fake.template)
        mock.post(f"{HA}/api/services/persistent_notification/create").mock(side_effect=fake.create)
        mock.post(f"{HA}/api/services/persistent_notification/dismiss").mock(side_effect=fake.dismiss)
        yield fake


@pytest.fixture
def connected(client, fake_ha):
    r = client.put("/api/v1/homeassistant/config", json={"url": HA + "/", "token": "good-token"})
    assert r.status_code == 200, r.text
    return client


def test_not_configured(client):
    status = client.get("/api/v1/homeassistant/status").json()
    assert status["configured"] is False and status["issue_count"] == 0
    assert client.post("/api/v1/homeassistant/sync").status_code == 502


def test_config_is_tested_before_saving(client, fake_ha):
    r = client.put("/api/v1/homeassistant/config", json={"url": HA, "token": "bad"})
    assert r.status_code == 502 and "rejected" in r.json()["detail"]
    assert client.get("/api/v1/homeassistant/status").json()["configured"] is False
    status = client.put("/api/v1/homeassistant/config", json={"url": HA, "token": "good-token"}).json()
    assert status["configured"] and status["source"] == "settings" and status["url"] == HA
    assert status["last_sync_at"] and status["token_set"]
    # token is kept when omitted, and never returned
    r = client.put("/api/v1/homeassistant/config", json={"url": HA, "monitor_label": "plant"})
    assert r.status_code == 200 and "token" not in r.json()


def test_environment_connection(client, fake_ha, monkeypatch):
    from app import config

    monkeypatch.setenv("PLANTASAURUS_HA_URL", HA)
    monkeypatch.setenv("PLANTASAURUS_HA_TOKEN", "good-token")
    config.get_settings.cache_clear()
    status = client.post("/api/v1/homeassistant/sync").json()
    assert status["source"] == "environment" and status["last_sync_error"] is None


def test_lists_labelled_devices(connected):
    zones = connected.get("/api/v1/homeassistant/devices", params={"role": "irrigation_zone"}).json()
    assert [d["device_id"] for d in zones] == ["zone1", "zone2"]
    monitors = connected.get("/api/v1/homeassistant/devices", params={"role": "plant_monitor"}).json()
    assert [(d["device_id"], d["name"]) for d in monitors] == [("mon1", "Flower Care 1")]
    assert monitors[0]["entities"] == ["sensor.mon1_moisture"]


def test_assign_devices_to_spots(connected, garden):
    bed, sill = garden["bed"]["id"], garden["sill"]["id"]
    r = connected.patch(f"/api/v1/spots/{bed}", json={"irrigation_zone_device_id": "zone1"})
    assert r.status_code == 200
    assert r.json()["irrigation_zone"] == {
        "device_id": "zone1", "name": "Front Lawn Zone", "area_name": "Garden", "problem": None, "missing_since": None
    }
    # wrong label / unknown device
    assert connected.patch(f"/api/v1/spots/{bed}", json={"irrigation_zone_device_id": "mon1"}).status_code == 422
    assert connected.patch(f"/api/v1/spots/{bed}", json={"plant_monitor_device_id": "other"}).status_code == 422
    assert connected.patch(f"/api/v1/spots/{bed}", json={"plant_monitor_device_id": "bad id!"}).status_code == 422
    # one monitor can't be in two spots, but a zone can water several
    assert connected.patch(f"/api/v1/spots/{bed}", json={"plant_monitor_device_id": "mon1"}).status_code == 200
    r = connected.patch(f"/api/v1/spots/{sill}", json={"plant_monitor_device_id": "mon1"})
    assert r.status_code == 409 and "Flowerbed" in r.json()["detail"]
    assert connected.patch(f"/api/v1/spots/{sill}", json={"irrigation_zone_device_id": "zone1"}).status_code == 200
    zones = connected.get("/api/v1/homeassistant/devices", params={"role": "irrigation_zone", "refresh": False}).json()
    assert sorted(next(d for d in zones if d["device_id"] == "zone1")["assigned_spot_ids"]) == sorted([bed, sill])
    # clearing
    r = connected.patch(f"/api/v1/spots/{bed}", json={"plant_monitor_device_id": None})
    assert r.json()["plant_monitor"] is None
    # can be set on create too
    spot = connected.post(
        "/api/v1/spots",
        json={"area_id": garden["garden"]["id"], "name": "Veg", "irrigation_zone_device_id": "zone2"},
    ).json()
    assert spot["irrigation_zone"]["name"] == "Veg Bed Zone"


def test_device_added_in_ha_after_last_sync_can_be_assigned(connected, fake_ha, garden):
    fake_ha.devices["zone3"] = {"name": "New Zone", "area": None, "labels": {"Irrigation Zone"}}
    r = connected.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"irrigation_zone_device_id": "zone3"})
    assert r.status_code == 200 and r.json()["irrigation_zone"]["name"] == "New Zone"


def test_detects_removed_and_unlabelled_devices(connected, fake_ha, garden):
    bed, sill = garden["bed"]["id"], garden["sill"]["id"]
    connected.patch(f"/api/v1/spots/{bed}", json={"irrigation_zone_device_id": "zone1"})
    connected.patch(f"/api/v1/spots/{sill}", json={"plant_monitor_device_id": "mon1"})
    assert connected.get("/api/v1/homeassistant/issues").json() == []

    del fake_ha.devices["zone1"]
    fake_ha.devices["mon1"]["labels"] = set()
    status = connected.post("/api/v1/homeassistant/sync").json()
    assert status["issue_count"] == 2
    issues = {i["role"]: i for i in connected.get("/api/v1/homeassistant/issues").json()}
    assert issues["irrigation_zone"]["problem"] == "deleted"
    assert issues["irrigation_zone"]["device_name"] == "Front Lawn Zone"  # last known name kept
    assert issues["irrigation_zone"]["missing_since"]
    assert issues["plant_monitor"]["problem"] == "label_removed"
    assert connected.get(f"/api/v1/spots/{bed}").json()["irrigation_zone"]["problem"] == "deleted"

    # users are alerted in HA too
    note = fake_ha.notifications["plantasaurus_missing_devices"]
    assert "Back Garden → Flowerbed" in note["message"] and "removed from Home Assistant" in note["message"]
    assert "no longer has its label" in note["message"]

    # unrelated edits still work while a device is missing
    assert connected.patch(f"/api/v1/spots/{bed}", json={"notes": "hi"}).status_code == 200
    # but a missing device can't be newly assigned elsewhere
    assert connected.patch(f"/api/v1/spots/{sill}", json={"irrigation_zone_device_id": "zone1"}).status_code == 422

    # fix: relabel the monitor in HA, remove the zone in Plantasaurus
    fake_ha.devices["mon1"]["labels"] = {"plant"}
    connected.patch(f"/api/v1/spots/{bed}", json={"irrigation_zone_device_id": None})
    assert connected.post("/api/v1/homeassistant/sync").json()["issue_count"] == 0
    assert "plantasaurus_missing_devices" not in fake_ha.notifications


def test_unreachable_ha_does_not_flag_devices(connected, fake_ha, garden):
    connected.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"irrigation_zone_device_id": "zone1"})
    fake_ha.down = True
    assert connected.post("/api/v1/homeassistant/sync").status_code == 502
    status = connected.get("/api/v1/homeassistant/status").json()
    assert "Could not reach" in status["last_sync_error"] and status["issue_count"] == 0


def test_notifications_can_be_disabled(connected, fake_ha, garden):
    connected.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"irrigation_zone_device_id": "zone1"})
    connected.put("/api/v1/homeassistant/config", json={"url": HA, "notify_in_ha": False})
    del fake_ha.devices["zone1"]
    assert connected.post("/api/v1/homeassistant/sync").json()["issue_count"] == 1
    assert fake_ha.notifications == {}


def test_background_sync(connected, fake_ha, garden):
    from app.services.homeassistant import run_background_sync

    connected.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"irrigation_zone_device_id": "zone1"})
    del fake_ha.devices["zone1"]
    run_background_sync()
    assert connected.get("/api/v1/homeassistant/status").json()["issue_count"] == 1


def test_config_requires_admin(connected):
    connected.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    connected.post("/api/v1/auth/logout")
    connected.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    assert connected.put("/api/v1/homeassistant/config", json={"url": HA}).status_code == 403
    assert connected.get("/api/v1/homeassistant/status").status_code == 200
