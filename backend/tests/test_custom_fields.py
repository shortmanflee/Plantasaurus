def test_custom_fields(client):
    r = client.post(
        "/api/v1/custom-fields",
        json={"entity": "plant", "key": "colour", "label": "Flower colour", "type": "select", "options": ["red", "blue"]},
    )
    assert r.status_code == 201
    client.post("/api/v1/custom-fields", json={"entity": "plant", "key": "height_cm", "label": "Height", "type": "number"})
    assert client.post(
        "/api/v1/custom-fields", json={"entity": "plant", "key": "x", "label": "X", "type": "select"}
    ).status_code == 422

    ok = client.post("/api/v1/plants", json={"common_name": "Rose", "attributes": {"colour": "red", "height_cm": "90"}})
    assert ok.status_code == 201 and ok.json()["attributes"] == {"colour": "red", "height_cm": 90.0}
    bad = client.post("/api/v1/plants", json={"common_name": "Rose", "attributes": {"colour": "green"}})
    assert bad.status_code == 422
    unknown = client.post("/api/v1/plants", json={"common_name": "Rose", "attributes": {"nope": 1}})
    assert unknown.status_code == 422

    pid = ok.json()["id"]
    patched = client.patch(f"/api/v1/plants/{pid}", json={"attributes": {"height_cm": None}}).json()
    assert patched["attributes"] == {"colour": "red"}

    # deleting a definition keeps stored values; editing other attrs doesn't drop them
    field_id = r.json()["id"]
    client.delete(f"/api/v1/custom-fields/{field_id}")
    patched = client.patch(f"/api/v1/plants/{pid}", json={"attributes": {"height_cm": 50}}).json()
    assert patched["attributes"] == {"colour": "red", "height_cm": 50.0}
