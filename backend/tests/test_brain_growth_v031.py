"""v0.31: саморазвитие мини-мозгов — смысл в ветках, выжимки, любопытство, новые мозги, карта."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, semantic
from backend.app.brain_growth import BrainGrowth
from backend.app.idle import IdleRuntime
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine


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


def say(client, text):
    response = client.post("/api/chat/messages", json={"text": text, "conversationId": "main"})
    assert response.status_code == 201, response.text
    return response.json()


class FakeMeaning:
    ready = True
    concepts = (("кофе", "эспрессо", "капучино"), ("бег", "марафон"))

    def encode(self, texts):
        return [semantic.normalize([1.0 if any(w in t.casefold() for w in g) else 0.0
                                    for g in self.concepts] + [0.1]) for t in texts]


def branch_members(path, term):
    with closing(db.connection(path)) as conn:
        return {r[0] for r in conn.execute(
            "SELECT m.content FROM memory_branches b JOIN memory_branch_members x ON x.branch_id=b.id "
            "JOIN memory_items m ON m.id=x.memory_id WHERE b.term=? AND b.depth=1", (term,))}


def test_branch_grows_by_meaning_not_only_words(app):
    client, path = app
    add(client, "Я пью кофе по утрам", "habits")
    add(client, "Я варю кофе дома", "habits")
    add(client, "Я заказываю эспрессо в обед", "habits")
    engine = MemoryEngine(path)
    engine.grow_branches()
    assert "Я заказываю эспрессо в обед" not in branch_members(path, "кофе")
    engine.semantic_index(FakeMeaning())
    engine.grow_branches()
    assert "Я заказываю эспрессо в обед" in branch_members(path, "кофе")
    # Модель смысла выключена — ветки снова только по словам.
    assert client.put("/api/memory/policy", json={"semantic_model": False}).status_code == 200
    engine.grow_branches()
    assert "Я заказываю эспрессо в обед" not in branch_members(path, "кофе")


def test_chat_gets_digest_of_the_mini_brain(app):
    client, path = app
    facts = ["Проект Kitsune пишу на Rust", "Kitsune хранит данные в SQLite",
             "Для Kitsune выбрал фреймворк Axum", "Kitsune открою на GitHub",
             "Логотип Kitsune рисует дизайнер", "Kitsune тестирую каждую неделю",
             "Kitsune работает на Linux", "Kitsune будет бесплатным",
             "Kitsune умеет искать заметки", "Kitsune синхронизирует файлы",
             "Kitsune показывает графики", "Kitsune поддерживает плагины",
             "Kitsune переводится на английский", "Kitsune запускается за секунду"]
    for fact in facts:
        add(client, fact, "projects")
    MemoryEngine(path).grow_branches()
    context = client.get("/api/memory/recall", params={"q": "Что с Kitsune?"}).json()["context"]
    # Поиск отдаёт несколько самых подходящих фактов, выжимка добавляет остальное коротко.
    assert "Выжимка мини-мозга «Kitsune»" in context
    selected = MemoryEngine(path).deep_recall("Что с Kitsune?", "main", False)
    assert sum(fact in context for fact in facts) > len(selected)
    # В облако выжимка не уходит без разрешения на передачу фактов.
    cloud_context = client.get("/api/memory/recall", params={"q": "Что с Kitsune?", "cloudMode": True}).json()
    assert "Kitsune" not in cloud_context["context"]


def test_curiosity_question_is_asked_once_and_respects_forgetting(app):
    client, path = app
    goal = add(client, "Хочу пробежать марафон", "goals")
    runtime = IdleRuntime(path, MemoryEngine(path))
    assert runtime.curiosity() == {"questions": 1}
    assert "curiosity" not in say(client, "Как дела?")  # на вопрос не отвечаем вопросом
    first = say(client, "Сегодня хороший день")
    assert first["curiosity"]["question"] == "Ты говорил: «Хочу пробежать марафон». К какому сроку хочешь это сделать?"
    assert "curiosity" not in say(client, "Пойду гулять")  # не чаще раза в шесть часов
    assert client.delete("/api/memory/facts/" + goal["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_curiosity").fetchone()[0] == 0


def test_curiosity_can_be_switched_off_and_dismissed(app):
    client, path = app
    add(client, "Хочу выучить японский", "goals")
    runtime = IdleRuntime(path, MemoryEngine(path))
    assert client.put("/api/memory/policy", json={"curiosity": False}).status_code == 200
    assert runtime.curiosity() == {"state": "off"}
    assert client.put("/api/memory/policy", json={"curiosity": True}).status_code == 200
    runtime.curiosity()
    question = say(client, "Сегодня хороший день")["curiosity"]
    assert client.post(f"/api/memory/curiosity/{question['id']}/dismiss").json() == {"dismissed": True}


def coffee_facts(client):
    for i, place in enumerate(["дома", "в офисе", "у друзей", "в кафе", "в поезде"]):
        add(client, f"Я пью кофе {place} номер {i}", "habits")
    for i, what in enumerate(["кофемашину", "кофе в зёрнах", "турку для кофе", "книгу про кофе"]):
        add(client, f"Хочу купить {what} кофе {i}", "goals")


def test_new_brain_is_only_proposed_and_created_after_yes(app):
    client, path = app
    coffee_facts(client)
    growth = BrainGrowth(path, MemoryEngine(path))
    report = growth.grow()
    assert report["proposals"] == 1 and report["subbrains"] > 0
    brain_map = client.get("/api/memory/brains/map").json()
    proposal = brain_map["proposals"][0]
    assert proposal["title"] == "Кофе" and set(proposal["brains"]) == {"habits", "goals"}
    assert not any(root["custom"] for root in brain_map["roots"])  # без «да» ничего не создано
    assert client.post("/api/memory/brains/proposals/" + proposal["id"], json={"accept": True}).json()["accepted"]
    brain_map = client.get("/api/memory/brains/map").json()
    custom = [root for root in brain_map["roots"] if root["custom"]]
    assert len(custom) == 1 and custom[0]["title"] == "Кофе" and custom[0]["facts"] == 9
    assert brain_map["proposals"] == []
    assert client.get("/api/memory/tree").json()["custom"][0]["title"] == "Кофе"
    assert client.delete("/api/memory/brains/custom/" + custom[0]["id"]).json() == {"removed": True}
    growth.grow()
    brain_map = client.get("/api/memory/brains/map").json()
    assert brain_map["proposals"] == [] and not any(root["custom"] for root in brain_map["roots"])


def test_declined_proposal_is_not_repeated(app):
    client, path = app
    coffee_facts(client)
    growth = BrainGrowth(path, MemoryEngine(path))
    growth.grow()
    proposal = growth.proposals()[0]
    assert growth.decide(proposal["id"], False) == {"accepted": False, "title": "Кофе"}
    growth.grow()
    assert growth.proposals() == []


def test_map_shows_growth_of_each_brain(app):
    client, path = app
    coffee_facts(client)
    runtime = IdleRuntime(path, MemoryEngine(path))
    runtime.grow()
    roots = {root["id"]: root for root in client.get("/api/memory/brains/map").json()["roots"]}
    assert set(roots) >= {"identity", "goals", "habits", "projects"}
    assert roots["habits"]["facts"] == 5 and roots["habits"]["branches"] >= 1
    assert roots["habits"]["growth"] == 0  # первый снимок — точка отсчёта
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("UPDATE memory_brain_history SET support=1, day=date('now','-6 day') WHERE node='habits'")
    roots = {root["id"]: root for root in client.get("/api/memory/brains/map").json()["roots"]}
    assert roots["habits"]["growth"] == 4
