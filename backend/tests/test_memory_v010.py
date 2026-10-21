"""Eight connected memory brains: classification, migration, consent and graph integrity."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import BRAINS, MemoryEngine, classify_brain


@pytest.fixture
def api(tmp_path, monkeypatch):
    # All tests stay local: no real Cloud.ru API requests or billing.
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    path = tmp_path / "eight-brains.sqlite3"
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as client:
        yield client, path


@pytest.mark.parametrize(
    ("text", "brain"),
    [
        ("Я люблю кошек", "identity"),
        ("Вчера гулял в парке", "episodes"),
        ("Хочу изучать Python", "goals"),
        ("Каждый день тренирую память", "habits"),
        ("Изучаю Python", "knowledge"),
        ("Мой друг помогает мне с Python", "relationships"),
        ("Разрабатываю проект Meiyuren", "projects"),
        ("Я решил перейти на Python", "decisions"),
        ("Я решил закончить проект Meiyuren", "decisions"),
        ("Моя сестра работает над проектом", "relationships"),
        ("Хочу развивать проект Meiyuren", "projects"),
    ],
)
def test_eight_brain_classification(text, brain):
    assert classify_brain(text) == brain


def test_eight_domains_are_stable_and_available(api):
    client, _ = api
    assert len(BRAINS) == len(set(BRAINS)) == 8
    assert BRAINS[:5] == ("identity", "episodes", "goals", "habits", "knowledge")
    assert BRAINS[5:] == ("relationships", "projects", "decisions")
    result = client.get("/api/memory/brains")
    assert result.status_code == 200
    assert set(result.json()["brains"]) == set(BRAINS)
    assert all(value == 0 for value in result.json()["brains"].values())


def test_manual_assignment_all_eight_survives_restart_and_respects_consent(api):
    client, path = api
    records = []
    for brain in BRAINS:
        response = client.post("/api/memory/facts", json={
            "content": "Мой факт в разделе " + brain, "brain": brain
        })
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["brain"] == brain
        assert data["cloudAllowed"] is False
        records.append(data)
    status = client.get("/api/memory/brains").json()
    assert status["brains"] == {brain: 1 for brain in BRAINS}
    assert client.get("/api/memory/policy").json()["allow_cloud_embeddings"] is False
    assert client.get("/api/memory/policy").json()["allow_cloud_facts"] is False
    assert client.get("/api/memory/recall", params={
        "q": "раздел projects", "conversationId": "main", "cloudMode": True,
    }).json()["context"] == ""
    with TestClient(create_app(path)) as reopened:
        persisted = reopened.get("/api/memory/brains").json()
        assert persisted["brains"] == {brain: 1 for brain in BRAINS}
        assert {fact["id"] for fact in reopened.get("/api/memory/facts").json()["facts"]} == {
            fact["id"] for fact in records
        }


def test_eight_brains_form_shared_graph_without_network_requests(api, monkeypatch):
    client, _ = api
    import httpx
    async def fail_network(*_args, **_kwargs):
        raise AssertionError("Local graph never calls Cloud.ru")
    monkeypatch.setattr(httpx.AsyncClient, "post", fail_network)
    items = []
    for brain in BRAINS:
        result = client.post("/api/memory/facts", json={
            "content": "Раздел " + brain + " изучает Python",
            "brain": brain,
        })
        assert result.status_code == 201, result.text
        items.append(result.json())
    stats = client.get("/api/memory/brains").json()
    assert stats["links"] > 0
    assert stats["neuralVectors"] == 0
    source = items[0]["id"]
    connections = client.get("/api/memory/brains/" + source + "/links").json()["connections"]
    assert any(x["item"]["brain"] in BRAINS[5:] for x in connections)
    rebuilt = client.post("/api/memory/brains/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["links"] > 0


def test_new_candidate_relationship_requires_approval(api):
    client, _ = api
    response = client.post("/api/chat/messages", json={
        "text": "Запомни: мой друг помогает мне с Python"
    })
    assert response.status_code == 201
    assert client.post("/api/memory/process").status_code == 200
    candidates = client.get("/api/memory/candidates").json()["candidates"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["brain"] == "relationships"
    assert client.get("/api/memory/facts").json()["facts"] == []
    approved = client.post(
        "/api/memory/candidates/" + candidate["id"] + "/review",
        json={"approve": True}
    )
    assert approved.status_code == 200
    item = approved.json()["item"]
    assert item["brain"] == "relationships"
    assert item["cloudAllowed"] is False


def test_manual_category_override_preserved_and_invalid_brains_rejected(api):
    client, path = api
    item = client.post("/api/memory/facts", json={
        "content": "Мой проект Meiyuren", "brain": "knowledge"
    }).json()
    assert item["brain"] == "knowledge"
    edit = client.put("/api/memory/facts/" + item["id"], json={
        "content": item["content"], "revision": item["revision"],
        "cloudAllowed": False, "brain": "decisions"
    })
    assert edit.status_code == 200
    assert edit.json()["brain"] == "decisions"
    assert edit.json()["revision"] == item["revision"] + 1
    with TestClient(create_app(path)) as reopened:
        fact = reopened.get("/api/memory/facts").json()["facts"][0]
        assert fact["brain"] == "decisions"
        assert reopened.get("/api/memory/brains").json()["brains"]["decisions"] == 1
    bad = client.post("/api/memory/facts", json={
        "content": "Недопустимая память", "brain": "ninth_brain"
    })
    assert bad.status_code == 422


def test_forgetting_new_brain_removes_connections_and_preserves_other_memories(api):
    client, path = api
    first = client.post("/api/memory/facts", json={
        "content": "План проекта Python", "brain": "projects"
    }).json()
    second = client.post("/api/memory/facts", json={
        "content": "Я решил продолжать проект Python", "brain": "decisions"
    }).json()
    assert client.get("/api/memory/brains").json()["links"] > 0
    assert client.delete("/api/memory/facts/" + first["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_links WHERE left_id=? OR right_id=?",
            (first["id"], first["id"])
        ).fetchone()[0] == 0
    retained = client.get("/api/memory/facts").json()["facts"]
    assert len(retained) == 1
    assert retained[0]["id"] == second["id"]


def test_v09_existing_brain_is_not_reclassified_during_v010_restart(api):
    client, path = api
    item = client.post("/api/memory/facts", json={
        "content": "Мой проект связан с другом", "brain": "identity"
    }).json()
    with TestClient(create_app(path)) as reopened:
        facts = reopened.get("/api/memory/facts").json()["facts"]
        assert facts[0]["brain"] == "identity"
        assert facts[0]["id"] == item["id"]
