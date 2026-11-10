def test_area_spot_position_crud(client):
    area = client.post("/api/v1/areas", json={"name": "Kitchen", "environment": "indoor"}).json()
    assert client.post("/api/v1/areas", json={"name": "Kitchen"}).status_code == 409
    spot = client.post(
        "/api/v1/spots",
        json={"area_id": area["id"], "name": "Shelf", "near_heat_source": True, "position_count": 2},
    ).json()
    assert spot["near_heat_source"] is True
    positions = client.get(f"/api/v1/spots/{spot['id']}/positions").json()
    assert [p["label"] for p in positions] == ["1", "2"]
    p3 = client.post("/api/v1/positions", json={"spot_id": spot["id"], "label": "3"}).json()
    assert client.patch(f"/api/v1/positions/{p3['id']}", json={"label": "back"}).json()["label"] == "back"
    assert client.patch(f"/api/v1/spots/{spot['id']}", json={"aspect": "SW"}).json()["aspect"] == "SW"
    assert client.patch(f"/api/v1/spots/{spot['id']}", json={"aspect": "up"}).status_code == 422
    assert client.patch(f"/api/v1/areas/{area['id']}", json={"environment": "greenhouse"}).json()["environment"] == "greenhouse"
    tree = client.get("/api/v1/locations/tree").json()
    assert tree[0]["spots"][0]["positions"][2]["label"] == "back"
    assert client.delete(f"/api/v1/positions/{p3['id']}").status_code == 204
    assert client.delete(f"/api/v1/areas/{area['id']}").status_code == 204
    assert client.get(f"/api/v1/spots/{spot['id']}").status_code == 404


def test_cannot_delete_occupied_or_historic_spot(client, garden):
    inst = client.post(
        "/api/v1/instances", json={"plant_id": garden["plant"]["id"], "spot_id": garden["bed"]["id"]}
    ).json()
    assert client.delete(f"/api/v1/spots/{garden['bed']['id']}").status_code == 409
    assert client.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"archived": True}).status_code == 409
    client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": garden["sill"]["id"]})
    assert client.delete(f"/api/v1/spots/{garden['bed']['id']}").status_code == 409  # history
    assert client.patch(f"/api/v1/spots/{garden['bed']['id']}", json={"archived": True}).status_code == 200
    # archived spots can't receive plants
    r = client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": garden["bed"]["id"]})
    assert r.status_code == 422
