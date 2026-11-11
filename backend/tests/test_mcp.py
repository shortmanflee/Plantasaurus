import asyncio
import base64
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from app.mcp_server import Backend, build_server
from tests.conftest import png_bytes


@pytest.fixture
def token(client) -> str:
    r = client.post("/api/v1/tokens", json={"name": "mcp"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.fixture
def run_tools(client, token):
    """Call MCP tools in-memory; they reach the app through the real REST API."""
    mcp = build_server(Backend.in_process(client.app, token))

    def run(*calls: tuple[str, dict]):
        async def go():
            async with Client(mcp) as c:
                return [(await c.call_tool(name, args)).data for name, args in calls]

        results = asyncio.run(go())
        return results[0] if len(results) == 1 else results

    return run


def test_plant_crud(run_tools):
    plant = run_tools(("create_plant", {"plant": {"common_name": "Basil", "category": "herb", "min_temp": 10}}))
    assert plant["id"] and plant["common_name"] == "Basil" and plant["total_instance_count"] == 0

    # Partial update: untouched fields keep their values, explicit null clears.
    updated = run_tools(("update_plant", {"plant_id": plant["id"], "changes": {"cultivar": "Genovese", "min_temp": None}}))
    assert updated["cultivar"] == "Genovese" and updated["category"] == "herb" and updated["min_temp"] is None

    page = run_tools(("list_plants", {"q": "basil"}))
    assert page["total"] == 1
    assert run_tools(("list_plant_categories", {})) == ["herb"]

    with pytest.raises(ToolError, match="No changes"):
        run_tools(("update_plant", {"plant_id": plant["id"], "changes": {}}))

    run_tools(("delete_plant", {"plant_id": plant["id"]}))
    with pytest.raises(ToolError, match="HTTP 404"):
        run_tools(("get_plant", {"plant_id": plant["id"]}))


def test_locations_crud(run_tools):
    area = run_tools(("create_area", {"area": {"name": "Kitchen", "environment": "indoor"}}))
    spot = run_tools(("create_spot", {"spot": {"area_id": area["id"], "name": "Sill", "aspect": "S", "position_count": 2}}))
    extra = run_tools(("create_position", {"position": {"spot_id": spot["id"], "label": "3"}}))
    assert [p["label"] for p in run_tools(("list_positions", {"spot_id": spot["id"]}))] == ["1", "2", "3"]

    run_tools(
        ("update_area", {"area_id": area["id"], "changes": {"description": "Bright"}}),
        ("update_spot", {"spot_id": spot["id"], "changes": {"sun_exposure": "full_sun"}}),
        ("update_position", {"position_id": extra["id"], "changes": {"notes": "corner"}}),
    )
    tree = run_tools(("get_location_tree", {}))
    assert tree[0]["description"] == "Bright"
    assert tree[0]["spots"][0]["sun_exposure"] == "full_sun" and tree[0]["spots"][0]["aspect"] == "S"

    with pytest.raises(ToolError, match="already exists"):
        run_tools(("create_area", {"area": {"name": "Kitchen"}}))

    run_tools(("delete_position", {"position_id": extra["id"]}), ("delete_spot", {"spot_id": spot["id"]}))
    run_tools(("delete_area", {"area_id": area["id"]}))
    assert run_tools(("list_areas", {})) == []


def test_instance_lifecycle(run_tools, garden):
    sill, bed, plant = garden["sill"], garden["bed"], garden["plant"]
    pos1 = garden["positions"][0]

    inst = run_tools(("create_instance", {"instance": {"plant_id": plant["id"], "position_id": pos1["id"], "nickname": "Monty"}}))
    assert inst["current_spot_id"] == sill["id"] and inst["status"] == "active"
    iid = inst["id"]

    watered = run_tools(("log_event", {"instance_id": iid, "event_type": "watered", "notes": "deep soak"}))
    moved = run_tools(("transplant_instance", {"instance_id": iid, "transplant": {"spot_id": bed["id"], "pot_size": "ground"}}))
    assert moved["spot_name"] == "Flowerbed"
    assessment = run_tools(("assess_instance", {"instance_id": iid, "assessment": {"overall": 4, "would_buy_again": "yes"}}))
    run_tools(("update_assessment", {"assessment_id": assessment["id"], "changes": {"overall": 5}}))
    assert run_tools(("get_assessment", {"assessment_id": assessment["id"]}))["overall"] == 5

    run_tools(("update_instance", {"instance_id": iid, "changes": {"notes": "doing well"}}))
    assert run_tools(("get_instance", {"instance_id": iid}))["notes"] == "doing well"

    # Lifecycle events are append-only; care events are not.
    with pytest.raises(ToolError, match="Input should be 'watered'"):
        run_tools(("log_event", {"instance_id": iid, "event_type": "moved"}))
    events = run_tools(("list_events", {"instance_id": iid, "event_type": ["planted"]}))
    with pytest.raises(ToolError, match="HTTP 409"):
        run_tools(("delete_event", {"event_id": events["items"][0]["id"]}))
    run_tools(("update_event", {"event_id": watered["id"], "changes": {"notes": "light"}}))
    run_tools(("delete_event", {"event_id": watered["id"]}))

    child = run_tools(("propagate_instance", {"instance_id": iid, "propagate": {"spot_id": sill["id"], "nickname": "Cutting"}}))
    assert child["parent_instance_id"] == iid

    retired = run_tools(
        ("retire_instance", {"instance_id": iid, "retire": {"status": "dead", "reason": "frost", "final_assessment": {"overall": 2}}})
    )
    assert retired["status"] == "dead" and retired["current_spot_id"] is None
    timeline = run_tools(("get_instance_timeline", {"instance_id": iid}))
    assert [t["event"]["event_type"] for t in timeline][:2] == ["died", "assessment"]

    active = run_tools(("list_instances", {"status": ["active"]}))
    assert [i["id"] for i in active["items"]] == [child["id"]]

    revived = run_tools(("revive_instance", {"instance_id": iid, "revive": {"spot_id": bed["id"]}}))
    assert revived["status"] == "active"
    run_tools(("delete_instance", {"instance_id": child["id"]}))
    assert run_tools(("get_plant_insights", {"plant_id": plant["id"]}))


def test_media_upload_and_view(run_tools, garden):
    inst = run_tools(("create_instance", {"instance": {"plant_id": garden["plant"]["id"]}}))
    media = run_tools(
        (
            "upload_media",
            {
                "image_base64": base64.b64encode(png_bytes()).decode(),
                "instance_id": inst["id"],
                "caption": "first leaf",
                "log_photo_event": True,
            },
        )
    )
    assert media["instance_id"] == inst["id"] and media["event_id"]

    run_tools(("update_media", {"media_id": media["id"], "changes": {"caption": "new leaf"}}))
    assert run_tools(("list_media", {"instance_id": inst["id"]}))["items"][0]["caption"] == "new leaf"
    run_tools(("delete_media", {"media_id": media["id"]}))

    with pytest.raises(ToolError, match="not valid base64"):
        run_tools(("upload_media", {"image_base64": "!!!"}))


def test_view_media_returns_image(client, token, garden):
    plant_id = garden["plant"]["id"]
    media = client.post(
        "/api/v1/media", files={"file": ("a.png", png_bytes(), "image/png")}, data={"plant_id": str(plant_id)}
    ).json()
    mcp = build_server(Backend.in_process(client.app, token))

    async def go():
        async with Client(mcp) as c:
            return await c.call_tool("view_media", {"media_id": media["id"]})

    result = asyncio.run(go())
    assert result.content[0].type == "image" and result.content[0].mime_type == "image/jpeg"


def test_admin_and_custom_fields(run_tools):
    field = run_tools(("create_custom_field", {"field": {"entity": "plant", "key": "origin", "label": "Origin", "type": "text"}}))
    run_tools(("update_custom_field", {"field_id": field["id"], "changes": {"help_text": "Where it came from"}}))
    assert run_tools(("list_custom_fields", {"entity": "plant"}))[0]["help_text"] == "Where it came from"
    run_tools(("delete_custom_field", {"field_id": field["id"]}))

    user = run_tools(("create_user", {"user": {"username": "bob", "password": "password123"}}))
    run_tools(("update_user", {"user_id": user["id"], "changes": {"display_name": "Bob"}}))
    assert {u["username"] for u in run_tools(("list_users", {}))} == {"admin", "bob"}
    run_tools(("delete_user", {"user_id": user["id"]}))

    assert run_tools(("whoami", {}))["username"] == "admin"
    created = run_tools(("create_api_token", {"name": "other"}))
    assert created["token"].startswith("pts_")
    run_tools(("revoke_api_token", {"token_id": created["id"]}))
    assert any(t["revoked_at"] for t in run_tools(("list_api_tokens", {})))


def test_non_admin_is_limited_by_api(client, run_tools):
    client.post("/api/v1/users", json={"username": "kim", "password": "password123"})
    kim = client.__class__(client.app)
    kim.post("/api/v1/auth/login", json={"username": "kim", "password": "password123"})
    kim_token = kim.post("/api/v1/tokens", json={"name": "kim"}).json()["token"]
    mcp = build_server(Backend.in_process(client.app, kim_token))

    async def go():
        async with Client(mcp) as c:
            await c.call_tool("create_custom_field", {"field": {"entity": "plant", "key": "x", "label": "X", "type": "text"}})

    with pytest.raises(ToolError, match="HTTP 403"):
        asyncio.run(go())


# ---- Mounted /mcp endpoint over real HTTP -----------------------------------


@pytest.fixture
def server_url(client):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def _http_client(url: str, token: str | None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Client(StreamableHttpTransport(url, headers=headers))


def test_mounted_endpoint_requires_token(server_url):
    r =httpx.post(f"{server_url}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    r = httpx.post(
        f"{server_url}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": "Bearer pts_nope"},
    )
    assert r.status_code == 401


def test_mounted_endpoint_runs_tools(server_url, token, client, garden):
    async def go():
        async with _http_client(f"{server_url}/mcp", token) as c:
            tools = {t.name for t in await c.list_tools()}
            me = (await c.call_tool("whoami", {})).data
            inst = (await c.call_tool("create_instance", {"instance": {"plant_id": garden["plant"]["id"]}})).data
            return tools, me, inst

    tools, me, inst = asyncio.run(go())
    assert {"create_plant", "move_instance", "delete_event"} <= tools
    assert me["username"] == "admin"
    assert client.get(f"/api/v1/instances/{inst['id']}").status_code == 200

    # A revoked token stops working straight away.
    token_id = next(t["id"] for t in client.get("/api/v1/tokens").json() if t["name"] == "mcp")
    client.delete(f"/api/v1/tokens/{token_id}")

    r = httpx.post(
        f"{server_url}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


# ---- On/off switch ----------------------------------------------------------

_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def test_switch_defaults_on_and_is_admin_only(client):
    assert client.get("/api/v1/mcp/status").json() == {"available": True, "enabled": True, "path": "mcp"}

    client.post("/api/v1/users", json={"username": "kim", "password": "password123"})
    kim = client.__class__(client.app)
    kim.post("/api/v1/auth/login", json={"username": "kim", "password": "password123"})
    assert kim.get("/api/v1/mcp/status").status_code == 200
    assert kim.put("/api/v1/mcp/config", json={"enabled": False}).status_code == 403


def test_switching_off_blocks_new_and_connected_clients(server_url, token, client):
    async def go():
        async with _http_client(f"{server_url}/mcp", token) as c:
            assert (await c.call_tool("whoami", {})).data["username"] == "admin"
            r = client.put("/api/v1/mcp/config", json={"enabled": False})
            assert r.json()["enabled"] is False
            with pytest.raises(Exception):
                await c.call_tool("whoami", {})

    asyncio.run(go())

    r = httpx.post(f"{server_url}/mcp", json=_LIST, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503 and "turned off" in r.json()["detail"]
    # The REST API itself is unaffected.
    assert httpx.get(f"{server_url}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    client.put("/api/v1/mcp/config", json={"enabled": True})

    async def again():
        async with _http_client(f"{server_url}/mcp", token) as c:
            return (await c.call_tool("whoami", {})).data

    assert asyncio.run(again())["username"] == "admin"


def test_env_var_removes_endpoint_and_locks_switch(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    monkeypatch.setenv("PLANTASAURUS_MCP_ENABLED", "false")
    config.get_settings.cache_clear()
    c = TestClient(create_app(config.get_settings()))
    c.post("/api/v1/auth/setup", json={"username": "admin", "password": "password123"})

    assert c.get("/api/v1/mcp/status").json() == {"available": False, "enabled": False, "path": "mcp"}
    r = c.put("/api/v1/mcp/config", json={"enabled": True})
    assert r.status_code == 409 and "PLANTASAURUS_MCP_ENABLED" in r.json()["detail"]
    assert c.post("/mcp", json=_LIST).status_code in (404, 405)
