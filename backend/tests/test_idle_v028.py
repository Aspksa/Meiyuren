"""v0.28: idle mode — what Meiyuren does locally while the user is away."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, idle as idle_module
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


def say(client, text, conversation="main"):
    response = client.post("/api/chat/messages", json={"text": text, "conversationId": conversation})
    assert response.status_code == 201, response.text
    assert client.post("/api/memory/process").status_code == 200


def runtime(path):
    return IdleRuntime(path, MemoryEngine(path))


def make_idle(rt, path):
    """Pretend the last activity was an hour ago."""
    rt._last_activity = 0
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("UPDATE messages SET sent_at=1")


def test_idle_run_reports_all_steps_and_briefing_is_shown_once(app):
    client, _ = app
    say(client, "Я разрабатываю проект Kitsune на Rust")
    result = client.post("/api/idle/run").json()
    assert result["ran"] and not result["interrupted"]
    assert set(result["report"]) == {"consolidation", "strength", "selfTraining", "meaning",
                                     "unfinished", "vectors", "health"}
    assert result["report"]["health"]["integrity"] == "ok"
    assert any("Kitsune" in item for item in result["report"]["unfinished"]["items"])
    briefing = client.get("/api/idle/briefing").json()["briefing"]
    assert briefing["id"] == result["id"]
    assert client.post("/api/idle/seen").json()["seen"] == 1
    assert client.get("/api/idle/briefing").json()["briefing"] is None
    status = client.get("/api/idle/status").json()
    assert status["externalCalls"] is False and status["lastRun"]["seen"]


def test_idle_waits_for_silence_and_interval(app):
    client, path = app
    say(client, "Привет")
    rt = runtime(path)
    assert rt.tick() == {"ran": False, "reason": "active"}
    make_idle(rt, path)
    assert rt.tick()["ran"]
    assert rt.tick() == {"ran": False, "reason": "interval"}


def test_user_message_pauses_idle_work(app, monkeypatch):
    client, path = app
    say(client, "Я изучаю Rust и компиляторы")
    rt = runtime(path)
    make_idle(rt, path)
    calls = []

    def user_writes():
        calls.append("strength")
        rt.touch()
        return {}

    monkeypatch.setattr(rt, "update_strength", user_writes)
    monkeypatch.setattr(rt, "self_train", lambda: calls.append("selfTraining"))
    result = rt.tick()
    assert result["interrupted"]
    assert calls == ["strength"]
    assert set(result["report"]) == {"consolidation", "strength"}


def test_chat_request_marks_activity(app):
    client, path = app
    status = client.get("/api/idle/status").json()
    assert not status["isIdle"]
    say(client, "Привет")
    assert client.get("/api/idle/status").json()["idleForMs"] < 60_000


def test_consolidation_merges_automatic_duplicates_and_keeps_manual(app):
    client, path = app
    engine = MemoryEngine(path)
    with closing(db.connection(path)) as conn:
        with conn:
            for i, text in enumerate(("Я изучаю Rust компиляторы парсеры вечерами",
                                      "Я изучаю Rust, компиляторы, парсеры вечерами!")):
                conn.execute(
                    "INSERT INTO memory_items(id,content,fingerprint,kind,status,conversation_id,"
                    "created_at,updated_at,brain) VALUES(?,?,?,'auto','confirmed','global',?,?,'knowledge')",
                    (f"a{i}", text, f"f{i}", 10 + i, 10 + i))
    client.post("/api/memory/facts", json={"content": "Я изучаю Rust компиляторы парсеры вечерами"})
    report = runtime(path).consolidate()
    assert report["merged"] == 1
    with closing(db.connection(path)) as conn:
        older = conn.execute("SELECT status,superseded_by FROM memory_items WHERE id='a0'").fetchone()
        manual = conn.execute("SELECT COUNT(*) FROM memory_items WHERE kind='manual' "
                              "AND status='confirmed'").fetchone()[0]
    assert tuple(older) == ("superseded", "a1")
    assert manual == 1
    assert engine.forget("a1")  # forgetting the winner removes the merged one too


def test_local_vectors_find_other_word_forms(app):
    client, _ = app
    client.post("/api/memory/facts", json={"content": "Я работаю программистом"})
    before = client.get("/api/memory/recall", params={"q": "программирование"}).json()
    assert before["context"] == ""
    client.post("/api/idle/run")
    after = client.get("/api/memory/recall", params={"q": "программирование"}).json()
    assert "программистом" in after["context"]
    unrelated = client.get("/api/memory/recall", params={"q": "какая погода в Москве"}).json()
    assert unrelated["context"] == ""


def test_strength_fades_without_use_and_grows_with_likes(app):
    client, path = app
    fresh = client.post("/api/memory/facts", json={"content": "Я люблю зелёный чай"}).json()
    old = client.post("/api/memory/facts", json={"content": "Я люблю горный велосипед"}).json()
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("UPDATE memory_items SET created_at=1 WHERE id=?", (old["id"],))
    client.post(f"/api/memory/deep/facts/{fresh['id']}/feedback", json={"helpful": True})
    report = runtime(path).update_strength()
    assert report["facts"] == 2 and report["fading"] == 1
    with closing(db.connection(path)) as conn:
        values = dict(conn.execute("SELECT memory_id,strength FROM memory_strength").fetchall())
    assert values[fresh["id"]] > values[old["id"]]


def test_private_items_are_not_in_briefing(app):
    client, path = app
    client.post("/api/memory/facts", json={"content": "Моя цель: вылечить диабет к лету"})
    client.post("/api/memory/facts", json={"content": "Моя цель: выпустить Kitsune к лету"})
    items = runtime(path).unfinished()["items"]
    assert not any("диабет" in item for item in items)
    assert any("Kitsune" in item for item in items)


def test_backup_is_daily_and_forgetting_deletes_snapshots(app):
    client, path = app
    fact = client.post("/api/memory/facts", json={"content": "Я люблю зелёный чай"}).json()
    rt = runtime(path)
    name = rt.health()["backup"]
    assert (rt.backup_dir() / name).exists()
    assert rt.health()["backup"] == name  # one snapshot per day
    assert client.delete("/api/memory/facts/" + fact["id"]).status_code == 200
    assert list(rt.backup_dir().glob("*.sqlite3")) == []
    assert idle_module.BACKUPS_KEPT == 3
