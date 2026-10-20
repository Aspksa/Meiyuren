"""Integration-тесты Meiyuren v0.6. Без внешних ключей и платных запросов."""
import json
import sqlite3
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    vault = {}
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: vault.get("key"))
    monkeypatch.setattr(cloud.keyring, "set_password", lambda *args: vault.__setitem__("key", args[2]))
    monkeypatch.setattr(cloud.keyring, "delete_password", lambda *_: vault.pop("key", None))
    with TestClient(create_app(tmp_path / "database.sqlite3"), headers={"X-Meiyuren-Client": "1"}) as server:
        yield server


def test_conversations_and_search(client):
    conversations = client.get("/api/conversations").json()["conversations"]
    assert any(item["id"] == "main" for item in conversations)
    new = client.post("/api/conversations", json={"title": "Путешествия"}).json()
    assert client.put("/api/conversations/" + new["id"], json={"title": "Отпуск"}).status_code == 200
    assert client.post("/api/chat/messages", json={"text": "Остров чудес", "conversationId": new["id"]}).status_code == 201
    assert client.post("/api/chat/messages", json={"text": "Главный разговор"}).status_code == 201
    assert len(client.get("/api/chat/messages?conversationId=" + new["id"]).json()["messages"]) == 2
    assert len(client.get("/api/chat/messages").json()["messages"]) == 2
    matches = client.get("/api/chat/search?q=Остров").json()["matches"]
    assert len(matches) == 1 and matches[0]["conversationId"] == new["id"]
    assert client.get("/api/chat/search?q=%25%25").json()["matches"] == []
    assert client.delete("/api/conversations/main").status_code == 409
    assert client.delete("/api/conversations/" + new["id"]).status_code == 200
    assert client.get("/api/chat/messages?conversationId=" + new["id"]).status_code == 404


def test_old_sqlite_history_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    db.initialise(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO messages(id,role,text,sent_at) VALUES ('old','user','Старое сообщение',123)")
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as server:
        rows = server.get("/api/chat/messages").json()["messages"]
        assert rows[0]["text"] == "Старое сообщение"
        assert rows[0]["id"] == "old"
        assert server.get("/api/conversations").status_code == 200


def test_facts_create_list_delete_persist(client):
    assert client.get("/api/memory/facts").json()["facts"] == []
    fact = client.post("/api/memory/facts", json={"content": "Нравится космос"}).json()
    assert fact["content"] == "Нравится космос"
    assert len(client.get("/api/memory/facts").json()["facts"]) == 1
    assert client.post("/api/memory/facts", json={"content": " "}).status_code == 422
    assert client.post("/api/memory/facts", json={"content": "x" * 501}).status_code == 422
    assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
    assert client.get("/api/memory/facts").json()["facts"] == []


def test_cloud_diagnostics_does_not_generate(client, monkeypatch):
    async def fake_models():
        return ["ai-sage/A", "ai-sage/B"]
    monkeypatch.setattr(cloud, "available_models", fake_models)
    no_key = client.get("/api/cloud/diagnostics").json()
    assert no_key["hasKey"] is False
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"},
                      headers={"Origin": "http://testserver"}).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/A", "enabled": True},
                      headers={"Origin": "http://testserver"}).status_code == 200
    status = client.get("/api/cloud/diagnostics").json()
    assert status["reachable"] is True and status["hasKey"] is True
    assert status["modelAvailable"] is True and status["modelsCount"] == 2
    assert isinstance(status["latencyMs"], int)


def test_demo_stream_without_key(client):
    request_id = str(uuid.uuid4())
    with client.stream("POST", "/api/chat/stream", json={"text": "Привет", "requestId": request_id}) as result:
        assert result.status_code == 200
        body = result.read().decode("utf-8")
    assert "event: delta" in body and "event: done" in body
    assert len(client.get("/api/chat/messages").json()["messages"]) == 2


def test_cloud_stream_and_same_id_replay(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None
        async def aiter_lines(self):
            for part in ("Привет", ", мир!"):
                yield "data: " + json.dumps({"choices": [{"delta": {"content": part}, "finish_reason": None}]})
                yield ""
            yield "data: [DONE]"
    calls = []

    @asynccontextmanager
    async def fake_stream(self, method, url, **kwargs):
        calls.append(kwargs["json"])
        assert kwargs["json"]["stream"] is True
        yield FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"},
                      headers={"Origin": "http://testserver"}).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/Test", "enabled": True},
                      headers={"Origin": "http://testserver"}).status_code == 200
    request_id = str(uuid.uuid4())
    data = {"text": "Скажи привет", "requestId": request_id}
    with client.stream("POST", "/api/chat/stream", json=data) as result:
        body = result.read().decode("utf-8")
    assert "event: done" in body and "Привет" in body
    assert len(calls) == 1
    with client.stream("POST", "/api/chat/stream", json=data) as again:
        repeated = again.read().decode("utf-8")
    assert "event: done" in repeated
    assert len(calls) == 1
    rows = client.get("/api/chat/messages").json()["messages"]
    assert rows[-1]["text"] == "Привет, мир!"


def test_interrupted_stream_keeps_payment_guard(client, monkeypatch):
    async def broken(*args, **kwargs):
        yield "Начало"
        raise cloud.CloudError("Связь прервалась.", 502)
    monkeypatch.setattr(cloud, "stream_cloud_reply", broken)
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"},
                      headers={"Origin": "http://testserver"}).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/Test", "enabled": True},
                      headers={"Origin": "http://testserver"}).status_code == 200
    data = {"text": "Прошу ответ", "requestId": str(uuid.uuid4())}
    with client.stream("POST", "/api/chat/stream", json=data) as res:
        body = res.read().decode()
    assert "event: delta" in body and "event: error" in body
    with client.stream("POST", "/api/chat/stream", json=data) as second:
        repeated = second.read().decode()
    assert "event: error" in repeated
    assert client.get("/api/chat/messages").json()["messages"] == []
