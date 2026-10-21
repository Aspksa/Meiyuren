"""v0.32: логический мозг — цепочки, время, противоречия, причины, правила, объяснения."""
from contextlib import closing
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.idle import IdleRuntime
from backend.app.main import create_app
from backend.app.memory_engine import INFERENCE_PREFIX, MemoryEngine
from backend.app.reasoning import Reasoner


@pytest.fixture
def app(tmp_path, monkeypatch):
    vault = {}
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: vault.get("secret"))
    monkeypatch.setattr(cloud.keyring, "set_password", lambda *args: vault.__setitem__("secret", args[2]))
    monkeypatch.setattr(cloud.keyring, "delete_password", lambda *_: vault.pop("secret", None))
    path = tmp_path / "memory.sqlite3"
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as client:
        yield client, path


def add(client, content, brain):
    response = client.post("/api/memory/facts", json={"content": content, "brain": brain})
    assert response.status_code in (200, 201), response.text
    return response.json()


def think(client, path, today=None):
    client.get("/api/memory/entities")  # граф людей и проектов обновлён
    return Reasoner(path, MemoryEngine(path)).rebuild(today)


def inferences(client):
    return client.get("/api/memory/inferences").json()["inferences"]


def test_chain_links_role_to_the_named_person(app):
    client, path = app
    add(client, "Мой брат Петя учится на юриста", "relationships")
    add(client, "Мой брат живёт в Казани", "relationships")
    think(client, path)
    chain = [i for i in inferences(client) if i["kind"] == "chain"]
    assert chain[0]["content"] == "«Мой брат живёт в Казани» — это про Петю (брат)"
    assert {p["content"] for p in chain[0]["because"]} == {
        "Мой брат живёт в Казани", "Мой брат Петя учится на юриста"}


def test_chain_does_not_guess_between_two_brothers(app):
    client, path = app
    add(client, "Мой брат Петя учится на юриста", "relationships")
    add(client, "Мой брат Коля работает врачом", "relationships")
    add(client, "Мой брат живёт в Казани", "relationships")
    think(client, path)
    assert not [i for i in inferences(client) if i["kind"] == "chain"]


def test_time_logic_and_overdue_question(app):
    client, path = app
    client.post("/api/chat/messages", json={"text": "Хочу сдать проект Kitsune в пятницу", "conversationId": "main"})
    client.post("/api/memory/process")
    due = date.fromisoformat(client.get("/api/memory/facts").json()["facts"][0]["dueDate"])
    think(client, path, due - timedelta(days=1))
    assert any(i["content"].endswith("— завтра") for i in inferences(client))
    think(client, path, due + timedelta(days=2))
    late = [i for i in inferences(client) if i["kind"] == "overdue"]
    assert late and late[0]["ask"] and "прошёл 2 дн. назад" in late[0]["content"]
    assert not any(i["content"].endswith("— завтра") for i in inferences(client))  # вчерашний вывод ушёл


def test_conflict_is_found_and_asked_in_chat(app):
    client, path = app
    add(client, "Я не люблю кофе", "identity")
    add(client, "Я люблю кофе", "identity")
    add(client, "Я пью чай по утрам", "habits")
    runtime = IdleRuntime(path, MemoryEngine(path))
    runtime.logic()
    conflict = [i for i in inferences(client) if i["kind"] == "conflict"]
    assert len(conflict) == 1
    assert conflict[0]["content"] == "Противоречие: «Я не люблю кофе» и «Я люблю кофе». Что верно сейчас?"
    runtime.curiosity()
    answer = client.post("/api/chat/messages", json={"text": "Привет", "conversationId": "main"}).json()
    assert answer["curiosity"]["question"] == conflict[0]["content"]


def test_habit_helps_goal(app):
    client, path = app
    add(client, "Хочу пробежать марафон", "goals")
    add(client, "Я тренируюсь к марафону каждое утро", "habits")
    add(client, "Я играю на гитаре", "habits")
    think(client, path)
    helps = [i["content"] for i in inferences(client) if i["kind"] == "helps"]
    assert helps == ["Привычка «Я тренируюсь к марафону каждое утро» помогает цели «Хочу пробежать марафон»"]


def test_rule_from_three_facts(app):
    client, path = app
    add(client, "По субботам я плаваю в бассейне", "habits")
    add(client, "В субботу хожу на тренировку", "habits")
    add(client, "По субботам играю в теннис", "habits")
    think(client, path)
    rules = [i for i in inferences(client) if i["kind"] == "rule"]
    assert rules[0]["content"] == "Правило: по субботам у тебя обычно бассейн, теннис, тренировка"
    assert len(rules[0]["because"]) == 3


def test_inference_explained_in_chat_rejected_and_forgotten(app):
    client, path = app
    first = add(client, "Я не люблю кофе", "identity")
    add(client, "Я люблю кофе", "identity")
    think(client, path)
    context = client.get("/api/memory/recall", params={"q": "Что насчёт кофе"}).json()["context"]
    assert INFERENCE_PREFIX + "Противоречие" in context
    cloud_context = client.get("/api/memory/recall", params={"q": "Что насчёт кофе", "cloudMode": True}).json()
    assert "Противоречие" not in cloud_context["context"]  # без разрешения в облако не уходит
    answer = client.post("/api/chat/messages", json={"text": "Что насчёт кофе", "conversationId": "main"}).json()
    explained = answer["memory"]["inferences"][0]
    assert len(explained["because"]) == 2
    assert client.post(f"/api/memory/inferences/{explained['id']}/reject").json() == {"rejected": True}
    think(client, path)
    assert inferences(client) == []  # отклонённый вывод не возвращается
    assert client.delete("/api/memory/facts/" + first["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_inferences").fetchone()[0] == 0
