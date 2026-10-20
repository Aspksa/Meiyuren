"""Проверки API и SQLite без подключения к внешней сети."""
import sqlite3

from fastapi.testclient import TestClient

from backend.app.main import create_app


def client(tmp_path):
    return TestClient(create_app(tmp_path / "meiyuren.sqlite3"))


def test_health_and_persistent_history(tmp_path):
    with client(tmp_path) as api:
        assert api.get("/api/health").json()["engine"] == "demo"
        assert api.get("/api/chat/messages").json() == {"messages": []}
        result = api.post("/api/chat/messages", json={"text": "Привет"}).json()
        assert result["user"]["text"] == "Привет"
        assert result["assistant"]["role"] == "assistant"
        assert result["user"]["id"] != result["assistant"]["id"]
    # Новый процесс/API читает ту же историю без восстановления из браузера.
    with client(tmp_path) as restarted:
        rows = restarted.get("/api/chat/messages").json()["messages"]
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert rows[0]["text"] == "Привет"


def test_validation_and_cleaning(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/api/chat/messages", json={"text": "   "}).status_code == 422
        assert api.post("/api/chat/messages", json={"text": "a" * 2001}).status_code == 422
        assert api.get("/api/chat/messages?limit=99999").status_code == 422
        assert api.get("/api/chat/messages?limit=0").status_code == 422
        assert api.post("/api/chat/messages", json={"text": "'; DROP TABLE messages;--"}).status_code == 201
        assert api.delete("/api/chat/messages").json() == {"deleted": 2}
        assert api.get("/api/chat/messages").json()["messages"] == []
        assert api.post("/api/chat/messages", json={"text": "Снова"}).status_code == 201


def test_explicit_memory_and_demo_use(tmp_path):
    with client(tmp_path) as api:
        assert api.get("/api/memory").json()["notes"] == ""
        saved = api.put("/api/memory", json={"notes": "Люблю кошек"}).json()
        assert saved["notes"] == "Люблю кошек"
        response = api.post("/api/chat/messages", json={"text": "Что ты помнишь?"}).json()
        assert "Люблю кошек" in response["assistant"]["text"]
        assert api.put("/api/memory", json={"notes": "x" * 4001}).status_code == 422
    with client(tmp_path) as restarted:
        assert restarted.get("/api/memory").json()["notes"] == "Люблю кошек"
        assert restarted.put("/api/memory", json={"notes": ""}).json()["notes"] == ""


def test_sqlite_uses_structured_tables(tmp_path):
    path = tmp_path / "db.sqlite3"
    with TestClient(create_app(path)) as api:
        assert api.post("/api/chat/messages", json={"text": "Проверка"}).status_code == 201
    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"messages", "profile_memory"}.issubset(tables)
