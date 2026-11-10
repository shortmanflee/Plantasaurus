import io
import warnings

import pytest
from fastapi.testclient import TestClient
from PIL import Image

warnings.filterwarnings("ignore", message="Cannot correctly sort tables")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from app import config
    from app.services import openplantbook

    monkeypatch.setenv("PLANTASAURUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PLANTASAURUS_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PLANTASAURUS_OPB_CLIENT_ID", "cid")
    monkeypatch.setenv("PLANTASAURUS_OPB_CLIENT_SECRET", "csecret")
    config.get_settings.cache_clear()
    openplantbook._client = None
    yield config.get_settings()
    config.get_settings.cache_clear()
    openplantbook._client = None


@pytest.fixture
def anon(settings) -> TestClient:
    from app.main import create_app

    return TestClient(create_app(settings))


@pytest.fixture
def client(anon) -> TestClient:
    r = anon.post("/api/v1/auth/setup", json={"username": "admin", "password": "password123"})
    assert r.status_code == 201, r.text
    return anon


def png_bytes(color=(0, 128, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def garden(client):
    """A small location hierarchy plus one plant."""
    living = client.post("/api/v1/areas", json={"name": "Living Room", "environment": "indoor"}).json()
    garden = client.post("/api/v1/areas", json={"name": "Back Garden", "environment": "outdoor"}).json()
    sill = client.post(
        "/api/v1/spots",
        json={"area_id": living["id"], "name": "Windowsill", "aspect": "S", "near_window": True, "position_count": 3},
    ).json()
    bed = client.post(
        "/api/v1/spots",
        json={"area_id": garden["id"], "name": "Flowerbed", "aspect": "N", "sun_exposure": "shade"},
    ).json()
    positions = client.get(f"/api/v1/spots/{sill['id']}/positions").json()
    plant = client.post("/api/v1/plants", json={"common_name": "Monstera", "scientific_name": "monstera deliciosa"}).json()
    return {"living": living, "garden": garden, "sill": sill, "bed": bed, "positions": positions, "plant": plant}
