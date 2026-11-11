import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.conftest import png_bytes


def _upload(client, **form):
    r = client.post("/api/v1/media", files={"file": ("p.png", png_bytes(), "image/png")}, data=form)
    assert r.status_code == 201, r.text
    return r.json()


def _make_backup(client) -> dict:
    r = client.post("/api/v1/backups")
    assert r.status_code == 202, r.text
    # TestClient runs background tasks before returning, so the job has finished.
    backup = client.get(f"/api/v1/backups/{r.json()['id']}").json()
    assert backup["status"] == "ready", backup
    return backup


def _download(client, backup) -> bytes:
    r = client.get(f"/api/v1/backups/{backup['id']}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    return r.content


def _restore_upload(client, content: bytes, name="backup.zip"):
    return client.post("/api/v1/backups/restore", files={"file": (name, content, "application/zip")})


def _snapshot(client) -> dict:
    instances = client.get("/api/v1/instances").json()["items"]
    return {
        "plants": client.get("/api/v1/plants").json()["items"],
        "tree": client.get("/api/v1/locations/tree").json(),
        "instances": [client.get(f"/api/v1/instances/{i['id']}").json() for i in instances],
        "timelines": [client.get(f"/api/v1/instances/{i['id']}/timeline").json() for i in instances],
        "media": client.get("/api/v1/media").json()["items"],
        "fields": client.get("/api/v1/custom-fields").json(),
    }


@pytest.fixture
def populated(client, garden):
    client.post("/api/v1/custom-fields", json={"entity": "plant", "key": "colour", "label": "Colour", "type": "text"})
    plant_img = _upload(client, plant_id=garden["plant"]["id"])
    client.patch(
        f"/api/v1/plants/{garden['plant']['id']}",
        json={"image_media_id": plant_img["id"], "attributes": {"colour": "green"}},
    )
    area_img = _upload(client)
    client.patch(f"/api/v1/areas/{garden['living']['id']}", json={"image_media_id": area_img["id"]})

    parent = client.post(
        "/api/v1/instances", json={"plant_id": garden["plant"]["id"], "position_id": garden["positions"][0]["id"]}
    ).json()
    client.post(f"/api/v1/instances/{parent['id']}/move", json={"spot_id": garden["bed"]["id"]})
    client.post(f"/api/v1/instances/{parent['id']}/assess", json={"overall": 4, "would_buy_again": "yes"})
    client.post("/api/v1/events", json={"instance_id": parent["id"], "event_type": "watered", "notes": "deep soak"})
    _upload(client, instance_id=parent["id"], caption="leafy", log_photo_event="true")
    r = client.post(f"/api/v1/instances/{parent['id']}/propagate", json={"spot_id": garden["sill"]["id"]})
    assert r.status_code in (200, 201), r.text
    return garden


def test_every_table_is_classified():
    from app.db import Base
    from app.services.backup import BACKED_UP_TABLES, EXCLUDED_TABLES

    assert not set(BACKED_UP_TABLES) & set(EXCLUDED_TABLES)
    assert set(BACKED_UP_TABLES) | set(EXCLUDED_TABLES) == set(Base.metadata.tables), (
        "Add new tables to BACKED_UP_TABLES or EXCLUDED_TABLES in app/services/backup.py"
    )


def test_backup_contents(client, populated):
    client.post("/api/v1/tokens", json={"name": "ha"})
    backup = _make_backup(client)
    assert backup["counts"]["plants"] == 1
    assert backup["counts"]["plant_instances"] == 2
    assert backup["counts"]["media"] == 3 and backup["counts"]["media_files"] == 6  # originals + thumbnails
    assert backup["size_bytes"] > 0 and backup["filename"].endswith(".zip")

    with zipfile.ZipFile(io.BytesIO(_download(client, backup))) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        everything = b"".join(zf.read(n) for n in names if not n.startswith("media/"))
    assert manifest["format"] == "plantasaurus-backup" and manifest["schema_revision"]
    assert manifest["users"] == {"1": "admin"}
    assert "data/plants.json" in names and "data/users.json" not in names
    assert sum(n.startswith("media/") for n in names) == 6
    # no credentials in the archive
    assert b"password_hash" not in everything and b"token_hash" not in everything and b"argon2" not in everything

    assert [b["id"] for b in client.get("/api/v1/backups").json()] == [backup["id"]]


def test_round_trip_restore(client, populated, settings):
    before = _snapshot(client)
    content = _download(client, _make_backup(client))

    # Change things: a new plant with a photo, a renamed area, a deleted event.
    extra = client.post("/api/v1/plants", json={"common_name": "Fern"}).json()
    extra_img = _upload(client, plant_id=extra["id"])
    client.patch(f"/api/v1/areas/{populated['garden']['id']}", json={"name": "Front Garden"})
    watered = next(
        t["event"] for t in before["timelines"][0] + before["timelines"][1] if t["event"]["event_type"] == "watered"
    )
    assert client.delete(f"/api/v1/events/{watered['id']}").status_code == 204
    from app.db import new_session
    from app.models import Media

    with new_session() as db:
        extra_file = settings.media_dir / db.get(Media, extra_img["id"]).path
    assert extra_file.exists()

    r = _restore_upload(client, content)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["counts"]["plants"] == 1 and result["counts"]["media_files"] == 6

    after = _snapshot(client)
    assert after == before
    # photos are served again, and files belonging only to the replaced data are gone
    for m in after["media"]:
        assert client.get(f"/api/v1/media/{m['id']}/file").status_code == 200
        assert client.get(f"/api/v1/media/{m['id']}/thumb").status_code == 200
    assert not extra_file.exists()

    # the data as it was just before the restore was backed up first
    safety = client.get(f"/api/v1/backups/{result['safety_backup_id']}").json()
    assert safety["status"] == "ready" and safety["note"] == "Automatic, before restore"
    assert safety["counts"]["plants"] == 2

    # restoring the safety backup brings the changes back
    r = client.post(f"/api/v1/backups/{safety['id']}/restore")
    assert r.status_code == 200, r.text
    assert {p["common_name"] for p in client.get("/api/v1/plants").json()["items"]} == {"Monstera", "Fern"}
    assert client.get(f"/api/v1/media/{extra_img['id']}/file").status_code == 200


def test_restore_into_fresh_install(client, populated, tmp_path_factory, monkeypatch):
    before = _snapshot(client)
    content = _download(client, _make_backup(client))

    from app import config
    from app.main import create_app

    monkeypatch.setenv("PLANTASAURUS_DATA_DIR", str(tmp_path_factory.mktemp("fresh")))
    config.get_settings.cache_clear()
    fresh = TestClient(create_app(config.get_settings()))
    assert fresh.post("/api/v1/auth/setup", json={"username": "admin", "password": "password123"}).status_code == 201
    r = _restore_upload(fresh, content)
    assert r.status_code == 200, r.text
    assert _snapshot(fresh) == before


def test_users_are_matched_by_username(client, garden):
    client.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    bob = TestClient(client.app)
    bob.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    inst = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"]}).json()
    by_admin = client.post("/api/v1/events", json={"instance_id": inst["id"], "event_type": "note"}).json()
    by_bob = bob.post("/api/v1/events", json={"instance_id": inst["id"], "event_type": "note"}).json()
    content = _download(client, _make_backup(client))

    bob_id = by_bob["user_id"]
    assert client.delete(f"/api/v1/users/{bob_id}").status_code == 204
    client.post("/api/v1/users", json={"username": "carol", "password": "password123"})  # may reuse bob's id
    assert _restore_upload(client, content).status_code == 200

    events = {e["id"]: e for e in client.get("/api/v1/events", params={"instance_id": inst["id"]}).json()["items"]}
    assert events[by_admin["id"]]["user_id"] == by_admin["user_id"]
    assert events[by_bob["id"]]["user_id"] is None
    # users themselves are untouched
    assert {u["username"] for u in client.get("/api/v1/users").json()} == {"admin", "carol"}


def _zip(files: dict[str, object]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, value in files.items():
            zf.writestr(name, value if isinstance(value, (str, bytes)) else json.dumps(value))
    return buf.getvalue()


MANIFEST = {"format": "plantasaurus-backup", "format_version": 1, "users": {}}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not a zip", "not a valid zip"),
        (_zip({"hello.txt": "hi"}), "not a Plantasaurus backup"),
        (_zip({"manifest.json": {**MANIFEST, "format_version": 99}}), "newer version"),
        (_zip({"manifest.json": {**MANIFEST, "schema_revision": "9999"}}), "newer version"),
        (_zip({"manifest.json": MANIFEST, "data/plants.json": "{oops"}), "damaged"),
        (
            _zip({"manifest.json": MANIFEST, "data/media.json": [{"id": 1, "path": "../../evil.png", "mime": "x"}]}),
            "invalid media path",
        ),
    ],
)
def test_restore_rejects_bad_archives(client, garden, content, message):
    r = _restore_upload(client, content)
    assert r.status_code == 422 and message in r.json()["detail"], r.text
    # nothing changed, and no safety backup was taken
    assert client.get("/api/v1/plants").json()["total"] == 1
    assert client.get("/api/v1/backups").json() == []


def test_failed_restore_keeps_data(client, garden, settings):
    # References a spot that doesn't exist, so the database part fails after media is extracted.
    bad = _zip(
        {
            "manifest.json": MANIFEST,
            "data/positions.json": [{"id": 1, "spot_id": 999, "label": "x", "sort_order": 0}],
            "data/media.json": [{"id": 1, "path": "2020/01/new.png", "mime": "image/png"}],
            "media/2020/01/new.png": png_bytes(),
        }
    )
    r = _restore_upload(client, bad)
    assert r.status_code == 422 and "inconsistent" in r.json()["detail"], r.text
    assert client.get("/api/v1/plants").json()["total"] == 1
    assert not (settings.media_dir / "2020/01/new.png").exists()


def test_admin_only(client):
    client.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    bob = TestClient(client.app)
    bob.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    assert bob.get("/api/v1/backups").status_code == 403
    assert bob.post("/api/v1/backups").status_code == 403
    assert _restore_upload(bob, b"x").status_code == 403


def test_delete_backup(client, garden, settings):
    backup = _make_backup(client)
    path = settings.data_dir / "backups" / backup["filename"]
    assert path.exists()
    assert client.delete(f"/api/v1/backups/{backup['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/v1/backups/{backup['id']}").status_code == 404


def test_failed_job_is_reported(client, garden, monkeypatch):
    from app.services import backup as backup_service

    def boom(dest):
        raise OSError("disk full")

    monkeypatch.setattr(backup_service, "write_archive", boom)
    job = client.post("/api/v1/backups").json()
    failed = client.get(f"/api/v1/backups/{job['id']}").json()
    assert failed["status"] == "failed" and failed["error"] == "disk full"
    assert client.get(f"/api/v1/backups/{job['id']}/download").status_code == 404


def test_interrupted_jobs_fail_on_startup(client, settings):
    from app.db import new_session
    from app.main import create_app
    from app.models import Backup

    with new_session() as db:
        db.add(Backup(status="running", counts={}))
        db.commit()
    (settings.data_dir / "backups" / "x.zip.partial").write_bytes(b"half")

    restarted = TestClient(create_app(settings))
    restarted.post("/api/v1/auth/login", json={"username": "admin", "password": "password123"})
    [job] = restarted.get("/api/v1/backups").json()
    assert job["status"] == "failed" and "restart" in job["error"]
    assert not (settings.data_dir / "backups" / "x.zip.partial").exists()


def _token_client(client, name="script") -> TestClient:
    token = client.post("/api/v1/tokens", json={"name": name}).json()["token"]
    return TestClient(client.app, headers={"Authorization": f"Bearer {token}"})


def test_full_flow_with_api_token(client, populated):
    """What a script or MCP client does: bearer token, no cookies, no polling."""
    api = _token_client(client)
    before = _snapshot(api)

    r = api.post("/api/v1/backups", params={"wait": "true"})
    assert r.status_code == 201, r.text
    backup = r.json()
    assert backup["status"] == "ready" and backup["counts"]["plants"] == 1
    assert [b["id"] for b in api.get("/api/v1/backups").json()] == [backup["id"]]
    content = _download(api, backup)

    api.post("/api/v1/plants", json={"common_name": "Fern"})
    r = api.post(f"/api/v1/backups/{backup['id']}/restore")  # JSON only, no upload
    assert r.status_code == 200, r.text
    assert _snapshot(api) == before

    api.post("/api/v1/plants", json={"common_name": "Fern"})
    r = _restore_upload(api, content)
    assert r.status_code == 200, r.text
    assert _snapshot(api) == before

    # the token still works after a restore (tokens aren't part of backups)
    assert api.get("/api/v1/auth/me").json()["username"] == "admin"


def test_wait_reports_failure(client, garden, monkeypatch):
    from app.services import backup as backup_service

    monkeypatch.setattr(backup_service, "write_archive", lambda dest: (_ for _ in ()).throw(OSError("disk full")))
    r = _token_client(client).post("/api/v1/backups", params={"wait": "true"})
    assert r.status_code == 201 and r.json()["status"] == "failed" and r.json()["error"] == "disk full"


def test_non_admin_token_is_refused(client):
    client.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    bob = TestClient(client.app)
    bob.post("/api/v1/auth/login", json={"username": "bob", "password": "password123"})
    api = _token_client(bob)
    assert api.post("/api/v1/backups", params={"wait": "true"}).status_code == 403
    assert api.post("/api/v1/backups/1/restore").status_code == 403
