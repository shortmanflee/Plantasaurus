from datetime import datetime, timedelta, timezone


def ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_lifecycle_is_traceable(client, garden):
    sill, bed, plant = garden["sill"], garden["bed"], garden["plant"]
    pos1, pos2 = garden["positions"][0], garden["positions"][1]

    inst = client.post(
        "/api/v1/instances",
        json={"plant_id": plant["id"], "position_id": pos1["id"], "source": "bought", "cost": 12.5, "occurred_at": ago(100)},
    ).json()
    assert inst["current_spot_id"] == sill["id"] and inst["position_label"] == "1"
    assert inst["area_name"] == "Living Room"
    assert len(inst["placements"]) == 1

    r = client.post(f"/api/v1/instances/{inst['id']}/move", json={"position_id": pos2["id"], "occurred_at": ago(50)})
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/instances/{inst['id']}/transplant",
        json={"spot_id": bed["id"], "pot_size": "ground", "occurred_at": ago(20)},
    )
    detail = r.json()
    assert detail["spot_name"] == "Flowerbed" and detail["current_position_id"] is None
    placements = detail["placements"]
    assert len(placements) == 3
    assert all(p["ended_at"] for p in placements[:2]) and placements[2]["ended_at"] is None

    # moving into the past before current placement is rejected
    r = client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": sill["id"], "occurred_at": ago(30)})
    assert r.status_code == 422
    # moving to the same place is rejected
    assert client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": bed["id"]}).status_code == 422
    # position in a different spot is rejected
    r = client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": bed["id"], "position_id": pos1["id"]})
    assert r.status_code == 422

    r = client.post(
        f"/api/v1/instances/{inst['id']}/retire",
        json={
            "status": "dead",
            "reason": "frost",
            "final_assessment": {"overall": 2, "would_buy_again": "no", "would_keep_location": "try_elsewhere"},
        },
    )
    retired = r.json()
    assert retired["status"] == "dead" and retired["current_spot_id"] is None and retired["end_reason"] == "frost"
    assert retired["placements"][-1]["ended_at"] is not None

    # retired instances can't be moved
    assert client.post(f"/api/v1/instances/{inst['id']}/move", json={"spot_id": sill["id"]}).status_code == 409

    timeline = client.get(f"/api/v1/instances/{inst['id']}/timeline").json()
    types = [t["event"]["event_type"] for t in timeline]
    assert types == ["died", "assessment", "transplanted", "moved", "planted"]
    assert timeline[1]["assessment"]["is_final"] is True
    assert timeline[2]["event"]["data"] == {"pot_size": "ground"}
    assert timeline[2]["event"]["from_spot_id"] == sill["id"] and timeline[2]["event"]["to_spot_id"] == bed["id"]

    # revive
    r = client.post(f"/api/v1/instances/{inst['id']}/revive", json={"spot_id": sill["id"], "notes": "resprouted"})
    assert r.json()["status"] == "active" and r.json()["spot_name"] == "Windowsill"


def test_instance_without_location_and_filters(client, garden):
    a = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"], "nickname": "Seedling"}).json()
    assert a["current_spot_id"] is None
    tl = client.get(f"/api/v1/instances/{a['id']}/timeline").json()
    assert tl[0]["event"]["event_type"] == "acquired"
    b = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"], "spot_id": garden["bed"]["id"]}).json()
    assert client.get("/api/v1/instances", params={"area_id": garden["garden"]["id"]}).json()["total"] == 1
    assert client.get("/api/v1/instances", params={"q": "seed"}).json()["items"][0]["id"] == a["id"]
    client.post(f"/api/v1/instances/{b['id']}/retire", json={"status": "given_away"})
    assert client.get("/api/v1/instances", params={"status": "active"}).json()["total"] == 1
    assert client.get("/api/v1/instances").json()["total"] == 2
    plant = client.get(f"/api/v1/plants/{garden['plant']['id']}").json()
    assert plant["active_instance_count"] == 1 and plant["total_instance_count"] == 2
    assert client.delete(f"/api/v1/plants/{garden['plant']['id']}").status_code == 409


def test_events_and_assessments(client, garden):
    inst = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"], "spot_id": garden["bed"]["id"]}).json()
    r = client.post("/api/v1/events", json={"instance_id": inst["id"], "event_type": "watered", "data": {"litres": 2}})
    assert r.status_code == 201
    ev = r.json()
    assert client.post("/api/v1/events", json={"instance_id": inst["id"], "event_type": "moved"}).status_code == 422
    assert client.patch(f"/api/v1/events/{ev['id']}", json={"notes": "deep soak"}).json()["notes"] == "deep soak"
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert client.post("/api/v1/events", json={"instance_id": inst["id"], "event_type": "fed", "occurred_at": future}).status_code == 422

    a = client.post(f"/api/v1/instances/{inst['id']}/assess", json={"health": 4, "overall": 4, "would_buy_again": "yes"})
    assert a.status_code == 201
    assessment = a.json()
    assert assessment["placement_id"] is not None
    assert client.patch(f"/api/v1/assessments/{assessment['id']}", json={"overall": 5}).json()["overall"] == 5
    assert client.post("/api/v1/assessments", json={"instance_id": inst["id"], "overall": 9}).status_code == 422

    planted = [e for e in client.get("/api/v1/events", params={"instance_id": inst["id"]}).json()["items"] if e["event_type"] == "planted"][0]
    assert client.delete(f"/api/v1/events/{planted['id']}").status_code == 409
    assert client.patch(f"/api/v1/events/{planted['id']}", json={"data": {"x": 1}}).status_code == 422
    assert client.delete(f"/api/v1/events/{ev['id']}").status_code == 204
    assert client.delete(f"/api/v1/assessments/{assessment['id']}").status_code == 204
    types = [t["event"]["event_type"] for t in client.get(f"/api/v1/instances/{inst['id']}/timeline").json()]
    assert types == ["planted"]


def test_propagate(client, garden):
    parent = client.post("/api/v1/instances", json={"plant_id": garden["plant"]["id"], "spot_id": garden["bed"]["id"]}).json()
    child = client.post(
        f"/api/v1/instances/{parent['id']}/propagate",
        json={"method": "cutting", "spot_id": garden["sill"]["id"], "quantity": 3},
    ).json()
    assert child["parent_instance_id"] == parent["id"] and child["quantity"] == 3 and child["source"] == "cutting"
    assert client.get(f"/api/v1/instances/{parent['id']}").json()["children_ids"] == [child["id"]]
    tl = client.get(f"/api/v1/instances/{parent['id']}/timeline").json()
    assert tl[0]["event"]["event_type"] == "propagated"
    assert tl[0]["event"]["data"]["child_instance_id"] == child["id"]


def test_insights(client, garden):
    plant, sill, bed = garden["plant"], garden["sill"], garden["bed"]
    good = client.post("/api/v1/instances", json={"plant_id": plant["id"], "spot_id": sill["id"], "occurred_at": ago(200)}).json()
    client.post(f"/api/v1/instances/{good['id']}/assess", json={"overall": 5, "would_buy_again": "yes", "assessed_at": ago(10)})
    bad = client.post("/api/v1/instances", json={"plant_id": plant["id"], "spot_id": bed["id"], "occurred_at": ago(100)}).json()
    client.post(f"/api/v1/instances/{bad['id']}/assess", json={"overall": 1, "assessed_at": ago(60)})
    client.post(f"/api/v1/instances/{bad['id']}/retire", json={"status": "dead", "reason": "Frost", "occurred_at": ago(50)})

    ins = client.get(f"/api/v1/plants/{plant['id']}/insights").json()
    assert ins["instances_total"] == 2
    assert ins["survival_rate"] == 0.5
    assert 49 < ins["avg_lifespan_days_dead"] < 51
    assert ins["by_spot"][0]["label"] == "Living Room › Windowsill" and ins["by_spot"][0]["avg_overall"] == 5
    assert ins["by_spot"][1]["deaths"] == 1
    assert {g["key"] for g in ins["by_environment"]} == {"indoor", "outdoor"}
    assert ins["end_reasons"] == {"frost": 1}
    assert ins["would_buy_again"] == {"yes": 1}
    assert ins["verdict"] == "Buy again"

    spot = client.get(f"/api/v1/spots/{bed['id']}/insights").json()
    assert spot["deaths"] == 1 and spot["history"][0]["outcome"] == "died"

    summary = client.get("/api/v1/insights/summary").json()
    assert summary["active_instances"] == 1 and summary["plants"] == 1
    assert summary["recent_losses"][0]["instance_id"] == bad["id"]
    assert summary["needs_assessment"] == []
