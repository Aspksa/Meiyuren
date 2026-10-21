"""v0.30: граф людей и проектов, модель смысла внутри приложения."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, semantic
from backend.app.idle import IdleRuntime
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine
from backend.app.understanding import entities


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


def test_entities_are_extracted_only_when_named():
    assert entities("Мой брат Петя учится на юриста") == [("person", "петя", "Петя", "брат")]
    found = {(k, n) for k, _, n, _ in entities("Я разрабатываю проект Kitsune на Rust")}
    assert found == {("project", "Kitsune"), ("tool", "Rust")}
    assert ("place", "Казань") in {(k, n) for k, _, n, _ in entities("Моя мама живёт в Казани")}
    assert ("person", "Лена") in {(k, n) for k, _, n, _ in entities("Вчера встретил Лену")}
    assert entities("Хочу выучить японский к декабрю") == []
    # Имя в начале предложения и латинское имя человека — не инструменты.
    found = {(k, n) for k, _, n, _ in entities("Петя работает в Яндексе")}
    assert found == {("person", "Петя"), ("org", "Яндекс")}
    assert [(k, n) for k, _, n, _ in entities("Мой брат John учится")] == [("person", "John")]
    assert entities("Сегодня хороший день") == []


def test_person_node_collects_all_facts(app):
    client, _ = app
    say(client, "Мой брат Петя учится на юриста. Он хочет переехать в Питер")
    say(client, "Я разрабатываю проект Kitsune на Rust")
    people = {e["name"]: e for e in client.get("/api/memory/entities").json()["entities"]}
    assert people["Петя"]["kind"] == "person" and people["Петя"]["role"] == "брат"
    assert people["Петя"]["facts"] == 2
    assert people["Kitsune"]["kind"] == "project"
    detail = client.get("/api/memory/entities/" + people["Петя"]["id"]).json()
    assert {f["content"] for f in detail["facts"]} == {
        "Мой брат Петя учится на юриста", "Петя (брат) хочет переехать в Питер"}
    assert "Питер" in {r["name"] for r in detail["related"]}


def test_question_about_person_or_role_recalls_everything(app):
    client, _ = app
    say(client, "Мой брат Петя учится на юриста. Он хочет переехать в Питер")
    for question in ("Что ты знаешь про Петю?", "Как дела у моего брата?"):
        recalled = client.get("/api/memory/recall", params={"q": question}).json()
        assert "учится на юриста" in recalled["context"], question
        assert "переехать в Питер" in recalled["context"], question


def test_forgetting_removes_entity_immediately(app):
    client, path = app
    say(client, "Мой брат Петя учится на юриста")
    client.get("/api/memory/entities")
    fact = client.get("/api/memory/facts").json()["facts"][0]
    assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_entities").fetchone()[0] == 0
    assert client.get("/api/memory/entities").json()["entities"] == []


class FakeMeaning:
    """Модель смысла для тестов: слова одного «смысла» дают один и тот же вектор."""
    ready = True
    concepts = (("кофе", "эспрессо", "капучино"), ("работ", "офис", "начальник"), ("чай",))

    def encode(self, texts):
        result = []
        for text in texts:
            low = text.casefold()
            vector = [1.0 if any(w in low for w in group) else 0.0 for group in self.concepts] + [0.1]
            result.append(semantic.normalize(vector))
        return result

    def status(self):
        return {"state": "ready"}


def test_meaning_model_finds_synonyms_without_shared_words(app, monkeypatch):
    client, path = app
    client.post("/api/memory/facts", json={"content": "Я пью эспрессо по утрам"})
    client.post("/api/memory/facts", json={"content": "Я люблю зелёный чай"})
    before = client.get("/api/memory/recall", params={"q": "что насчёт кофе"}).json()
    assert "эспрессо" not in before["context"]
    fake = FakeMeaning()
    monkeypatch.setattr(semantic, "model_for", lambda _path: fake)
    report = IdleRuntime(path, MemoryEngine(path)).meaning()
    assert report["state"] == "ready" and report["updated"] == 2
    after = client.get("/api/memory/recall", params={"q": "что насчёт кофе"}).json()
    assert "эспрессо" in after["context"]
    assert "зелёный чай" not in after["context"]


def test_meaning_model_respects_switch_and_forgetting(app, monkeypatch):
    client, path = app
    fact = client.post("/api/memory/facts", json={"content": "Я пью эспрессо по утрам"}).json()
    monkeypatch.setattr(semantic, "model_for", lambda _path: FakeMeaning())
    runtime = IdleRuntime(path, MemoryEngine(path))
    assert client.put("/api/memory/policy", json={"semantic_model": False}).status_code == 200
    assert runtime.meaning() == {"state": "off"}
    assert client.put("/api/memory/policy", json={"semantic_model": True}).status_code == 200
    runtime.meaning()
    assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_semantic_vectors").fetchone()[0] == 0


def test_semantic_status_without_model(app):
    client, _ = app
    status = client.get("/api/memory/semantic").json()
    assert status["model"] == semantic.MODEL
    assert status["enabled"] is True
    assert status["state"] != "ready"
