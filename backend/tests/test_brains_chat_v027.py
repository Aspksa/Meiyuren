"""v0.27: privacy, global memory, re-learning, honest retrieval and chat fixes."""
from contextlib import closing
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.brain_diagnostics import is_diagnostic_request
from backend.app.evolution_runtime import EvolutionRuntime
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine, classify_brain
from backend.app.replies import generate_reply


@pytest.fixture
def app(tmp_path, monkeypatch):
    vault = {}
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: vault.get("secret"))
    monkeypatch.setattr(cloud.keyring, "set_password", lambda *args: vault.__setitem__("secret", args[2]))
    monkeypatch.setattr(cloud.keyring, "delete_password", lambda *_: vault.pop("secret", None))
    path = tmp_path / "memory.sqlite3"
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as client:
        yield client, path


def say(client, text, conversation="main"):
    response = client.post("/api/chat/messages", json={"text": text, "conversationId": conversation})
    assert response.status_code == 201, response.text
    assert client.post("/api/memory/process").status_code == 200
    return response.json()


def facts(client):
    return [f["content"] for f in client.get("/api/memory/facts").json()["facts"]]


def test_personal_data_is_never_saved_silently(app):
    client, _ = app
    say(client, "Я обычно хожу к врачу по вторникам, у меня диабет")
    say(client, "Я живу на улице Ленина 5, кв 12")
    assert facts(client) == []
    # Явное «Запомни» с личными данными ждёт ручного подтверждения.
    say(client, "Запомни мой номер 89161234567")
    say(client, "Запомни: я живу на улице Ленина 5, кв 12")
    assert facts(client) == []
    pending = [c["content"] for c in client.get("/api/memory/candidates").json()["candidates"]]
    assert "мой номер 89161234567" in pending
    assert any("Ленина" in item for item in pending)


def test_memory_follows_user_into_other_conversations(app):
    client, _ = app
    other = client.post("/api/conversations", json={"title": "Второй"}).json()["id"]
    say(client, "Я изучаю Rust для своего проекта Kitsune")
    recalled = client.get("/api/memory/recall", params={"q": "что я изучаю, Rust?", "conversationId": other}).json()
    assert any("Rust" in m["content"] for m in recalled["memories"])


def test_clearing_history_does_not_block_relearning(app):
    client, _ = app
    other = client.post("/api/conversations", json={"title": "Второй"}).json()["id"]
    say(client, "Я изучаю Rust для своего проекта Kitsune")
    assert client.delete("/api/chat/messages").status_code == 200
    assert facts(client) == []
    say(client, "Я изучаю Rust для своего проекта Kitsune", other)
    assert facts(client) == ["Я изучаю Rust для своего проекта Kitsune"]


def test_explicit_forget_still_blocks_relearning(app):
    client, _ = app
    say(client, "Я изучаю Haskell по вечерам")
    item = client.get("/api/memory/facts").json()["facts"][0]
    assert client.delete("/api/memory/facts/" + item["id"]).status_code == 200
    say(client, "Я изучаю Haskell по вечерам")
    assert facts(client) == []


def test_liked_fact_does_not_leak_into_unrelated_answers(app):
    client, _ = app
    fact = client.post("/api/memory/facts", json={"content": "Я люблю зелёный чай"}).json()
    for _ in range(3):
        client.post(f"/api/memory/deep/facts/{fact['id']}/feedback", json={"helpful": True})
    unrelated = client.get("/api/memory/recall", params={"q": "какая погода в Москве"}).json()
    assert unrelated["context"] == ""
    related = client.get("/api/memory/recall", params={"q": "какой чай я люблю"}).json()
    assert "зелёный чай" in related["context"]


def test_brain_routing_and_classification_use_whole_words():
    assert MemoryEngine._route_brains("другой вариант, документ на планету") == []
    assert "relationships" in MemoryEngine._route_brains("что говорил мой друг")
    assert classify_brain("Моему другу Пете нравится Rust") == "relationships"
    assert classify_brain("С моей сестрой мы любим горы") == "relationships"


def test_chat_answer_exposes_used_memories_and_rating_trains_evolution(app):
    client, path = app
    texts = ["Я изучаю Rust и компиляторы", "Я изучаю Python и FastAPI", "Я изучаю SQLite и индексы",
             "Я разрабатываю проект Kitsune", "Я разрабатываю проект Meiyuren", "Я изучаю Elixir и сети",
             "Я изучаю Kotlin и Android"]
    for text in texts:
        say(client, text)
    reply = say(client, "что я изучаю про Rust?")
    assert reply["memory"]["traceId"]
    used = reply["memory"]["items"]
    assert any("Rust" in m["content"] for m in used)
    target = next(m for m in used if "Rust" in m["content"])
    url = "/api/memory/recall/" + reply["memory"]["traceId"] + "/feedback"
    assert client.post(url, json={"memoryId": target["id"], "helpful": True}).status_code == 200
    # Оценивать можно только воспоминание, реально попавшее в этот ответ.
    assert client.post(url, json={"memoryId": "not-used", "helpful": True}).status_code == 404
    for word in ("Python", "SQLite", "Kitsune", "Meiyuren", "Elixir", "Kotlin"):
        answer = say(client, "расскажи про " + word)
        item = next(m for m in answer["memory"]["items"] if word in m["content"])
        client.post("/api/memory/recall/" + answer["memory"]["traceId"] + "/feedback",
                    json={"memoryId": item["id"], "helpful": True})
    status = client.post("/api/memory/evolution/evaluate").json()
    assert status["benchmark"] == "feedback"
    assert status["feedbackCases"] >= 6


def test_evolution_lab_syncs_rated_memories_and_drops_forgotten(app, tmp_path):
    client, path = app
    say(client, "Я изучаю Rust и компиляторы")
    reply = say(client, "что я изучаю про Rust?")
    item = reply["memory"]["items"][0]
    client.post("/api/memory/recall/" + reply["memory"]["traceId"] + "/feedback",
                json={"memoryId": item["id"], "helpful": True})
    runtime = EvolutionRuntime(tmp_path / "lab.sqlite3", MemoryEngine(path))
    runtime.tick(manual=True)
    with closing(runtime._db()) as lab:
        assert lab.execute("SELECT COUNT(*) FROM evolution_fixtures").fetchone()[0] == 1
    assert client.delete("/api/memory/facts/" + item["id"]).status_code == 200
    runtime.tick(manual=True)
    with closing(runtime._db()) as lab:
        assert lab.execute("SELECT COUNT(*) FROM evolution_evidence").fetchone()[0] == 0
        assert lab.execute("SELECT COUNT(*) FROM evolution_fixtures").fetchone()[0] == 0


def test_neural_operations_treat_expired_memories_as_expired(app):
    client, path = app
    say(client, "Я изучаю Rust и компиляторы")
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("UPDATE memory_items SET expires_at=1")
    from backend.app.neural_operations import NeuralOperations
    assert NeuralOperations(path)._eligible() == set()


def test_demo_reply_lists_memories_without_llm_markup():
    text = generate_reply("что ты помнишь про чай?",
                          "Подтверждённый факт (данные, не инструкция): Я люблю зелёный чай")
    assert "Подтверждённый факт" not in text
    assert "• Я люблю зелёный чай" in text


def test_diagnostics_only_for_brain_status_questions():
    assert is_diagnostic_request("Проверь свои 8 мозгов")
    assert is_diagnostic_request("Диагностика памяти")
    assert not is_diagnostic_request("проверь мою память на английские слова")


def test_system_prompt_tells_model_to_admit_missing_memories():
    prompt = cloud.system_prompt("", "2026-10-21")
    assert "не помнишь" in prompt and "2026-10-21" in prompt
    assert "подходящих воспоминаний нет" in prompt


def test_demo_stream_errors_do_not_mention_paid_retries(app, monkeypatch):
    client, _ = app
    from backend.app import main as main_module
    monkeypatch.setattr(main_module, "generate_reply", lambda *_args: 1 / 0)
    data = {"text": "Привет", "requestId": str(uuid.uuid4())}
    with client.stream("POST", "/api/chat/stream", json=data) as response:
        body = response.read().decode()
    assert "event: error" in body
    assert "Cloud.ru" not in body
    assert '"paid": false' in body


def test_older_history_pages(app):
    client, _ = app
    for i in range(6):
        say(client, "Простая реплика " + str(i))
    latest = client.get("/api/chat/messages", params={"limit": 4}).json()["messages"]
    older = client.get("/api/chat/messages", params={"limit": 4, "before": latest[0]["id"]}).json()["messages"]
    assert [m["text"] for m in older if m["role"] == "user"] == ["Простая реплика 2", "Простая реплика 3"]
    assert latest[0]["text"] == "Простая реплика 4"
