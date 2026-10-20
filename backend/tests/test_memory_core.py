"""Memory Core integration: local-only, no Cloud.ru billing."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, history
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine


@pytest.fixture
def client(tmp_path, monkeypatch):
    vault = {}
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: vault.get("secret"))
    monkeypatch.setattr(cloud.keyring, "set_password", lambda *args: vault.__setitem__("secret", args[2]))
    monkeypatch.setattr(cloud.keyring, "delete_password", lambda *_: vault.pop("secret", None))
    with TestClient(create_app(tmp_path / "memory.sqlite3"),
                    headers={"X-Meiyuren-Client": "1"}) as app:
        yield app


def test_migration_and_legacy_facts_preserved(tmp_path):
    path = tmp_path / "old.sqlite3"
    db.initialise(path)
    history.initialise(path)
    history.add_fact(path, "Люблю шахматы")
    with TestClient(create_app(path)) as app:
        facts = app.get("/api/memory/facts").json()["facts"]
        assert len(facts) == 1
        assert facts[0]["content"] == "Люблю шахматы"
        assert facts[0]["kind"] == "legacy"
        assert facts[0]["sourceMessageId"] is None
        assert facts[0]["cloudAllowed"] is False
    assert (tmp_path / "old.sqlite3.before-memory-core.bak").exists()
    with TestClient(create_app(path)) as app:
        assert len(app.get("/api/memory/facts").json()["facts"]) == 1


def test_manual_fact_private_by_default_and_explicit_opt_in(client):
    policy = client.get("/api/memory/policy").json()
    assert policy["allow_cloud_facts"] is False
    assert policy["allow_cloud_notes"] is False
    fact = client.post("/api/memory/facts", json={"content": "Люблю шахматы"}).json()
    assert fact["cloudAllowed"] is False
    explanation = client.get("/api/memory/facts/" + fact["id"] + "/explain").json()
    assert explanation["sourceAvailable"] is False
    assert explanation["item"]["revision"] == 1
    engine = client.app  # Integration policy is exposed only through API.
    assert client.put("/api/memory/policy", json={"allow_cloud_facts": True}).status_code == 200
    updated = client.put("/api/memory/facts/" + fact["id"],
                         json={"content": "Люблю шахматы", "cloudAllowed": True, "revision": 1})
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["cloudAllowed"] is True
    assert client.put("/api/memory/facts/" + fact["id"],
                      json={"content": "Changed", "revision": 1}).status_code == 409


def test_sensitive_information_cannot_be_memorized_or_transferred(client):
    bad = client.post("/api/memory/facts", json={"content": "API key: secret-value-123"})
    assert bad.status_code == 422
    assert "secret-value-123" not in str(bad.json())
    assert client.put("/api/memory", json={"notes": "Мой пароль: something"}).status_code == 200
    denied = client.put("/api/memory/policy", json={"allow_cloud_notes": True})
    assert denied.status_code == 422
    assert client.get("/api/memory/policy").json()["allow_cloud_notes"] is False
    assert client.put("/api/memory", json={"notes": "Важная заметка"}).status_code == 200
    assert client.put("/api/memory/policy", json={"allow_cloud_notes": True}).status_code == 200
    assert client.put("/api/memory", json={"notes": "token is secret"}).status_code == 422


def test_recall_uses_only_relevant_and_cloud_permitted_facts(client, tmp_path):
    path = tmp_path / "memory.sqlite3"
    engine = MemoryEngine(path)
    one = client.post("/api/memory/facts", json={"content": "Люблю шахматы", "cloudAllowed": True}).json()
    client.post("/api/memory/facts", json={"content": "Покупаю апельсины", "cloudAllowed": False})
    assert "шахматы" in engine.prepare("Мне нравятся шахматы?", "main", False)
    assert "апельсины" not in engine.prepare("Мне нравятся шахматы?", "main", False)
    assert engine.prepare("Мне нравятся шахматы?", "main", True) == ""
    assert client.put("/api/memory/policy", json={"allow_cloud_facts": True}).status_code == 200
    assert "шахматы" in engine.prepare("Мне нравятся шахматы?", "main", True)
    assert "апельсины" not in engine.prepare("Мне нравятся шахматы?", "main", True)
    assert client.delete("/api/memory/facts/" + one["id"]).status_code == 200
    assert "шахматы" not in engine.prepare("Мне нравятся шахматы?", "main", True)


def test_observe_review_source_and_forgetting(client, tmp_path):
    path = tmp_path / "memory.sqlite3"
    response = client.post("/api/chat/messages", json={"text": "Запомни: что я люблю собак"})
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    assert client.post("/api/memory/process").status_code == 200
    candidates = client.get("/api/memory/candidates").json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["sourceMessageId"] == user_id
    assert client.post("/api/memory/candidates/" + candidates[0]["id"] + "/review",
                       json={"approve": True}).status_code == 200
    facts = client.get("/api/memory/facts").json()["facts"]
    assert len(facts) == 1
    info = client.get("/api/memory/facts/" + facts[0]["id"] + "/explain").json()
    assert info["source"]["id"] == user_id
    assert client.delete("/api/memory/facts/" + facts[0]["id"]).status_code == 200
    engine = MemoryEngine(path)
    engine.initialize()
    assert client.get("/api/memory/facts").json()["facts"] == []
    engine.observe(response.json(), "main")
    engine.process_pending()
    assert client.get("/api/memory/candidates").json()["candidates"] == []


def test_summary_is_reviewed_and_never_exported_by_default(client, tmp_path):
    for i in range(6):
        response = client.post("/api/chat/messages", json={"text": "Сообщение номер " + str(i)})
        assert response.status_code == 201
    client.post("/api/memory/process")
    summaries = client.get("/api/memory/summaries").json()["summaries"]
    assert len(summaries) == 1
    assert summaries[0]["status"] == "draft"
    assert summaries[0]["cloudAllowed"] is False
    assert client.post("/api/memory/summaries/main/review", json={"approve": True}).status_code == 200
    assert MemoryEngine(tmp_path / "memory.sqlite3").prepare("что обсуждали раньше", "main", True) == ""
    assert "Локальная выписка" in MemoryEngine(tmp_path / "memory.sqlite3").prepare("что обсуждали раньше", "main", False)


def test_erasing_chat_clears_derived_memories(client):
    first = client.post("/api/chat/messages", json={"text": "Запомни: люблю горячий шоколад"}).json()
    client.post("/api/memory/process")
    candidate = client.get("/api/memory/candidates").json()["candidates"][0]
    client.post("/api/memory/candidates/" + candidate["id"] + "/review", json={"approve": True})
    assert client.get("/api/memory/facts").json()["facts"]
    assert client.delete("/api/chat/messages").status_code == 200
    assert client.get("/api/memory/facts").json()["facts"] == []
    assert client.get("/api/memory/candidates").json()["candidates"] == []


def test_cross_site_memory_changes_rejected(client):
    assert client.put("/api/memory/policy", json={"allow_cloud_facts": True},
                      headers={"X-Meiyuren-Client": ""}).status_code == 403
    assert client.post("/api/memory/process", headers={"Origin": "http://attacker.invalid"}).status_code == 403


def test_manual_memory_survives_restart_and_forgotten_stays_deleted(client, tmp_path):
    fact = client.post("/api/memory/facts", json={"content": "Особенно нравится математика"}).json()
    assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
    path = tmp_path / "memory.sqlite3"
    with TestClient(create_app(path)) as restarted:
        assert restarted.get("/api/memory/facts").json()["facts"] == []
