"""Regression suite: unified SQLite memory, privacy, migrations, deletion."""
import sqlite3

from fastapi.testclient import TestClient
from backend.app import db, history
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine


def api(tmp_path):
    return TestClient(create_app(tmp_path / "memory.sqlite3"), headers={"X-Meiyuren-Client": "1"})


def test_legacy_migration_and_backup(tmp_path):
    path = tmp_path / "memory.sqlite3"
    db.initialise(path)
    history.initialise(path)
    old = history.add_fact(path, "Люблю кошек")
    message = history.append_exchange(path, "Привет", "Ответ", "main")
    with api(tmp_path) as client:
        facts = client.get("/api/memory/facts").json()["facts"]
        assert len(facts) == 1 and facts[0]["id"] == old["id"]
        assert facts[0]["kind"] == "legacy" and facts[0]["sourceMessageId"] is None
        assert client.get("/api/chat/messages").json()["messages"][0]["id"] == message["user"]["id"]
    assert (tmp_path / "memory.sqlite3.before-memory-core.bak").exists()
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM memory_facts").fetchone()[0] == 0
    with api(tmp_path) as client:
        assert len(client.get("/api/memory/facts").json()["facts"]) == 1
        assert client.delete("/api/memory/facts/" + old["id"]).status_code == 200
    with api(tmp_path) as client:
        assert client.get("/api/memory/facts").json()["facts"] == []


def test_recall_filters_cloud_policy_and_relevance(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        item = client.post("/api/memory/facts", json={"content": "Люблю кофе"}).json()
        assert "Люблю кофе" in engine.prepare("кофе", "main", False)
        assert "Люблю кофе" not in engine.prepare("кофе", "main", True)
        assert "Люблю кофе" not in engine.prepare("погода", "main", False)
        assert client.put("/api/memory/policy", json={"allow_cloud_facts": True}).status_code == 200
        assert "Люблю кофе" not in engine.prepare("кофе", "main", True)
        item = client.put("/api/memory/facts/" + item["id"], json={
            "content": "Люблю кофе", "cloudAllowed": True, "revision": item["revision"]
        }).json()
        assert item["revision"] == 2
        assert "Люблю кофе" in engine.prepare("кофе", "main", True)
        assert client.put("/api/memory/facts/" + item["id"], json={
            "content": "Обновление", "cloudAllowed": True, "revision": 1
        }).status_code == 409
        assert client.put("/api/memory/policy", json={"allow_cloud_facts": False}).status_code == 200
        assert "Люблю кофе" not in engine.prepare("кофе", "main", True)


def test_notes_local_and_secret_policy(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        assert client.put("/api/memory", json={"notes": "Люблю яблоки"}).status_code == 200
        assert "Люблю яблоки" in engine.prepare("яблоки", "main", False)
        assert "Люблю яблоки" not in engine.prepare("яблоки", "main", True)
        assert client.put("/api/memory/policy", json={"allow_cloud_notes": True}).status_code == 200
        assert "Люблю яблоки" in engine.prepare("яблоки", "main", True)
        assert client.put("/api/memory", json={"notes": "API key: secret-value"}).status_code == 422
        assert client.post("/api/memory/facts", json={"content": "Пароль secret-value"}).status_code == 422
        assert client.put("/api/memory/policy", json={"allow_cloud_notes": False}).status_code == 200
        assert client.put("/api/memory", json={"notes": "API key: secret-value"}).status_code == 200
        assert client.put("/api/memory/policy", json={"allow_cloud_notes": True}).status_code == 422


def test_candidates_require_approval_and_link_sources(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        exchange = client.post("/api/chat/messages", json={"text": "Запомни, что мне нравится космос"}).json()
        engine.process_pending(30)
        candidates = client.get("/api/memory/candidates").json()["candidates"]
        assert len(candidates) == 1 and client.get("/api/memory/facts").json()["facts"] == []
        reviewed = client.post("/api/memory/candidates/" + candidates[0]["id"] + "/review",
                               json={"approve": True}).json()
        item = reviewed["item"]
        assert item["sourceMessageId"] == exchange["user"]["id"]
        explain = client.get("/api/memory/facts/" + item["id"] + "/explain").json()
        assert explain["sourceAvailable"] is True
        assert "Запомни" in explain["source"]["text"]
        assert client.post("/api/memory/candidates/" + candidates[0]["id"] + "/review",
                           json={"approve": True}).status_code == 404


def test_revision_search_and_forget(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        fact = client.post("/api/memory/facts", json={"content": "Предпочитаю RPG"}).json()
        current = client.put("/api/memory/facts/" + fact["id"], json={
            "content": "Предпочитаю стратегии", "cloudAllowed": False, "revision": 1
        }).json()
        assert current["revision"] == 2
        detail = client.get("/api/memory/facts/" + fact["id"] + "/explain").json()
        assert detail["revisions"][0]["content"] == "Предпочитаю RPG"
        assert "Предпочитаю стратегии" in engine.prepare("стратегии", "main", False)
        assert "Предпочитаю RPG" not in engine.prepare("RPG", "main", False)
        assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
        assert "Предпочитаю стратегии" not in engine.prepare("стратегии", "main", False)
        assert client.get("/api/memory/facts/" + fact["id"] + "/explain").status_code == 404
        with sqlite3.connect(tmp_path / "memory.sqlite3") as conn:
            assert conn.execute("SELECT count(*) FROM memory_revisions").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM memory_fts").fetchone()[0] == 0


def test_draft_summary_and_per_conversation_forget(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        for i in range(6):
            assert client.post("/api/chat/messages", json={"text": "Путешествие в горы " + str(i)}).status_code == 201
        engine.process_pending(50)
        summaries = client.get("/api/memory/summaries").json()["summaries"]
        assert len(summaries) == 1 and summaries[0]["status"] == "draft"
        assert "выписка" not in engine.prepare("вспомни разговор", "main", False).lower()
        assert client.post("/api/memory/summaries/main/review", json={"approve": True}).status_code == 200
        assert "выписка" in engine.prepare("вспомни разговор", "main", False).lower()
        assert "выписка" not in engine.prepare("вспомни разговор", "main", True).lower()
        assert client.delete("/api/chat/messages").status_code == 200
        assert client.get("/api/memory/summaries").json()["summaries"] == []


def test_deleting_conversation_cleans_derived_memory(tmp_path):
    engine = MemoryEngine(tmp_path / "memory.sqlite3")
    with api(tmp_path) as client:
        conv = client.post("/api/conversations", json={"title": "Тест"}).json()
        msg = client.post("/api/chat/messages", json={
            "text": "Запомни, что люблю плавание", "conversationId": conv["id"]
        }).json()
        engine.process_pending(20)
        candidate = client.get("/api/memory/candidates").json()["candidates"][0]
        assert candidate["sourceMessageId"] == msg["user"]["id"]
        assert client.post("/api/memory/candidates/" + candidate["id"] + "/review",
                           json={"approve": True}).status_code == 200
        assert len(engine.items()) == 1
        assert client.delete("/api/conversations/" + conv["id"]).status_code == 200
        assert engine.items() == [] and engine.candidates() == []


def test_no_external_ai_calls_and_local_origin_guard(tmp_path):
    with api(tmp_path) as client:
        assert client.get("/api/memory/status").status_code == 200
        assert client.post("/api/memory/process").status_code == 200
        assert client.get("/api/memory/policy").json()["allow_cloud_facts"] is False
        assert client.put("/api/memory/policy", json={"allow_cloud_facts": True},
                          headers={"X-Meiyuren-Client": ""}).status_code == 403
