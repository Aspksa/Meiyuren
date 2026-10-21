"""v0.29, «Понимание 2.0» слой 1: экзамен из живых фраз и проверка каждого механизма."""
from contextlib import closing
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import _keywords
from backend.app.understanding import change_topic, due_date, resolve_pronoun, statements


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
    return client.get("/api/memory/facts").json()["facts"]


# Экзамен: фраза → (ожидаемый кусок факта, мозг) или None, если запоминать нельзя.
EXAM = [
    ("Я изучаю Rust", ("изучаю Rust", "knowledge")),
    ("Привет! Я изучаю Scala", ("изучаю Scala", "knowledge")),
    ("Я изучаю Elixir. А ты?", ("изучаю Elixir", "knowledge")),
    ("Спасибо! Я пишу на Go", ("пишу на Go", "knowledge")),
    ("Сегодня начал учить Kotlin", ("учить Kotlin", "knowledge")),
    ("Мой брат Петя учится на юриста", ("Петя учится на юриста", "relationships")),
    ("Я занимаюсь плаванием по субботам", ("занимаюсь плаванием", "identity")),
    ("Я обычно встаю в шесть утра", ("встаю в шесть", "habits")),
    ("Я бросил курить", ("бросил курить", "habits")),
    ("Мне нравится джаз", ("нравится джаз", "identity")),
    ("Я разрабатываю проект Kitsune", ("проект Kitsune", "projects")),
    ("Хочу выучить японский к декабрю", ("японский к декабрю", "goals")),
    ("Я решил писать бэкенд на FastAPI", ("FastAPI", "decisions")),
    ("Моя цель: пробежать марафон", ("пробежать марафон", "goals")),
    # Нельзя: вопросы, догадки, чужие слова, личное без «Запомни», болтовня.
    ("Как дела?", None),
    ("Допустим, я живу в Токио", None),
    ("Кажется, я люблю джаз", None),
    ("Говорят, Rust сложный", None),
    ("У меня диабет, я хожу к врачу", None),
    ("Привет, Мэйюрэн!", None),
    ("Я живу на улице Ленина 5", None),
    ("«Я изучаю Haskell» — сказал мой друг", None),
]


def test_exam_recall_and_precision(app):
    client, _ = app
    hits = misses = false_saves = wrong_brain = 0
    for i, (phrase, expected) in enumerate(EXAM):
        conversation = client.post("/api/conversations", json={"title": f"t{i}"}).json()["id"]
        before = {f["id"] for f in facts(client)}
        say(client, phrase, conversation)
        new = [f for f in facts(client) if f["id"] not in before]
        if expected is None:
            false_saves += bool(new)
            assert not new, (phrase, new)
            continue
        part, brain = expected
        match = [f for f in new if part in f["content"]]
        if match:
            hits += 1
            wrong_brain += match[0]["brain"] != brain
        else:
            misses += 1
    positives = sum(1 for _, e in EXAM if e)
    # Было (v0.28): 7 из 14. Стало: 14 из 14. Порог: полнота ≥ 90%, ноль лишнего, мозги ≥ 85%.
    assert hits / positives >= 0.9, (hits, misses)
    assert false_saves == 0
    assert (hits - wrong_brain) / hits >= 0.85, wrong_brain


def test_message_is_split_into_several_facts(app):
    client, _ = app
    say(client, "Привет! Я изучаю Rust. Я разрабатываю проект Kitsune. А ты чем занята?")
    contents = sorted(f["content"] for f in facts(client))
    assert contents == ["Я изучаю Rust", "Я разрабатываю проект Kitsune"]


def test_pronoun_is_resolved_from_previous_statement(app):
    client, _ = app
    say(client, "Мой брат Петя учится на юриста. Он хочет переехать в Питер")
    contents = {f["content"]: f["brain"] for f in facts(client)}
    assert contents.get("Петя (брат) хочет переехать в Питер") == "relationships"
    # И через отдельное сообщение: «она» не подходит к брату и не угадывается.
    say(client, "Она любит кошек")
    assert not any("кошек" in c for c in contents)
    assert not any("кошек" in f["content"] for f in facts(client))


def test_goal_gets_due_date_and_context_shows_it(app):
    client, _ = app
    say(client, "Хочу сдать проект Kitsune в пятницу")
    item = facts(client)[0]
    assert item["dueDate"]
    due = date.fromisoformat(item["dueDate"])
    assert due.weekday() == 4 and 0 < (due - date.today()).days <= 7
    recalled = client.get("/api/memory/recall", params={"q": "когда сдать Kitsune"}).json()
    assert "(срок: " + item["dueDate"] + ")" in recalled["context"]


def test_quitting_closes_the_old_fact(app):
    client, _ = app
    say(client, "Я обычно курю после обеда")
    say(client, "Я бросил курить")
    contents = [f["content"] for f in facts(client)]
    assert contents == ["Я бросил курить"]
    say(client, "Я работаю в Яндексе")
    say(client, "Я больше не работаю в Яндексе")
    assert "Я работаю в Яндексе" not in [f["content"] for f in facts(client)]


def test_follow_up_question_uses_previous_message(app):
    client, _ = app
    say(client, "Мой брат Петя учится на юриста")
    say(client, "Расскажи про Петю")
    answer = say(client, "А что ты о нём помнишь?")
    assert any("Петя" in m["content"] for m in answer["memory"]["items"])


def test_word_forms_and_short_words_match():
    assert _keywords("Я пишу на Go") & _keywords("писать на Go")
    assert "go" in _keywords("Я пишу на Go")
    assert _keywords("люблю чай") & _keywords("какой чай")
    assert _keywords("Я курю") <= _keywords("курить") | _keywords("Я курю")
    assert _keywords("курить") <= _keywords("Я курю после обеда")


def test_rules_layer_units():
    wednesday = int(datetime(2026, 10, 21, 12).timestamp() * 1000)
    assert statements("Привет! Я изучаю Rust. А ты?") == ["Я изучаю Rust"]
    assert due_date("сдать в пятницу", wednesday) == date(2026, 10, 23)
    assert due_date("к декабрю", wednesday) == date(2026, 12, 1)
    assert due_date("через неделю", wednesday) == date(2026, 10, 28)
    assert due_date("Python 3.11", wednesday) is None
    assert change_topic("Я бросил курить") == "курить"
    assert change_topic("Я не люблю кофе") is None
    assert resolve_pronoun("Она любит кошек", "Моя сестра Аня учится") == "Аня (сестра) любит кошек"
    assert resolve_pronoun("Она любит кошек", "Мой брат Петя учится") is None


def test_old_message_sources_still_respected(app):
    client, path = app
    say(client, "Я изучаю Haskell по вечерам")
    item = facts(client)[0]
    assert client.delete("/api/memory/facts/" + item["id"]).status_code == 200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_excluded_sources").fetchone()[0] == 1
    say(client, "Я изучаю Haskell по вечерам")
    assert facts(client) == []
