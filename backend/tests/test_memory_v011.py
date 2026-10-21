"""v0.11: automatic private learning and self-growing recursive memory branches."""
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import BRAINS, MemoryEngine, MAX_BRANCH_DEPTH


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    path=tmp_path / "memory-autonomous.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        yield client,path


def manual(client, text, brain=None):
    response=client.post("/api/memory/facts",json={"content":text,"brain":brain})
    assert response.status_code==201,response.text
    return response.json()


def say(client,text):
    response=client.post("/api/chat/messages",json={"text":text})
    assert response.status_code==201,response.text
    assert client.post("/api/memory/process").status_code==200
    return response.json()


def test_autonomous_learning_without_proposals_or_cloud_cost(app,monkeypatch):
    client,path=app
    calls=[]
    async def no_network(*_args,**_kwargs):
        calls.append(1)
        raise AssertionError("Autonomous growth must never request Cloud.ru")
    monkeypatch.setattr(httpx.AsyncClient,"post",no_network)
    assert client.get("/api/memory/policy").json()["auto_growth"] is True
    exchange=say(client,"Я изучаю Python")
    facts=client.get("/api/memory/facts").json()["facts"]
    assert len(facts)==1
    fact=facts[0]
    assert fact["kind"]=="auto" and fact["brain"]=="knowledge"
    assert fact["cloudAllowed"] is False
    assert fact["sourceMessageId"]==exchange["user"]["id"]
    assert client.get("/api/memory/candidates").json()["candidates"]==[]
    assert client.get("/api/memory/policy").json()["allow_cloud_facts"] is False
    assert calls==[]
    assert client.get("/api/memory/facts/"+fact["id"]+"/explain").json()["source"]["id"]==exchange["user"]["id"]


def test_recursive_branch_growth_with_three_levels_and_stable_ids(app):
    client,_=app
    phrases=[
        "Изучаю Python FastAPI SQLite в проекте Alpha",
        "Изучаю Python FastAPI SQLite через тесты Beta",
        "Изучаю Python FastAPI Redis через уроки",
        "Изучаю Python React в свободное время",
    ]
    items=[manual(client,phrase,"knowledge") for phrase in phrases]
    tree=client.get("/api/memory/tree").json()
    assert len(tree["roots"])==8
    assert all(root in tree["roots"] for root in BRAINS)
    branches=[r for r in tree["branches"] if r["brain"]=="knowledge" and r["depth"]>0]
    assert branches
    assert any(r["depth"]>=3 for r in branches)
    assert max(r["depth"] for r in branches)<=MAX_BRANCH_DEPTH
    before={r["id"] for r in branches}
    status=client.get("/api/memory/status").json()
    assert status["autonomousBranches"]>=len(branches)
    rebuilt=client.post("/api/memory/tree/rebuild")
    assert rebuilt.status_code==200
    after={r["id"] for r in client.get("/api/memory/tree").json()["branches"] if r["depth"]>0}
    assert before==after
    with closing(db.connection(_)) as conn:
        links=conn.execute(
            "SELECT COUNT(*) FROM memory_branch_members WHERE memory_id=?",(items[0]["id"],)
        ).fetchone()[0]
    assert links>=2


def test_branches_pruned_after_forgetting_and_no_ghost_members(app):
    client,path=app
    first=manual(client,"Изучаю Kotlin библиотеку","knowledge")
    second=manual(client,"Изучаю Kotlin разработку","knowledge")
    branches=client.get("/api/memory/tree").json()["branches"]
    kotlin=[b for b in branches if "kotlin" in b["term"]]
    assert kotlin
    removed=kotlin[0]["id"]
    assert client.delete("/api/memory/facts/"+first["id"]).status_code==200
    tree=client.get("/api/memory/tree").json()
    assert not any(b["id"]==removed for b in tree["branches"])
    with closing(db.connection(path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_branch_members WHERE memory_id=?",(first["id"],)
        ).fetchone()[0]==0
    assert len(client.get("/api/memory/facts").json()["facts"])==1
    assert client.get("/api/memory/facts").json()["facts"][0]["id"]==second["id"]


def test_auto_updates_explicitly_reversed_preferences(app):
    client,_=app
    say(client,"Я люблю кофе")
    old=client.get("/api/memory/facts").json()["facts"][0]
    say(client,"Я больше не люблю кофе")
    facts=client.get("/api/memory/facts").json()["facts"]
    assert len(facts)==1
    assert "не люблю кофе" in facts[0]["content"]
    with closing(db.connection(_)) as conn:
        previous=conn.execute(
            "SELECT status,superseded_by FROM memory_items WHERE id=?",(old["id"],)
        ).fetchone()
    assert previous["status"]=="superseded"
    assert previous["superseded_by"]==facts[0]["id"]
    assert client.get("/api/memory/candidates").json()["candidates"]==[]


def test_private_ambiguous_and_sensitive_content_is_not_autosaved(app):
    client,_=app
    for text in [
        "Запомни: мой пароль: secret12345",
        "Я изучаю медицинский диагноз",
        "Я планирую банковский кредит",
        "А что если я изучаю Python?",
        "«Я изучаю Python»",
        "Привет, как дела?",
    ]:
        say(client,text)
    assert client.get("/api/memory/facts").json()["facts"]==[]


def test_long_term_branches_do_not_expose_cloud_denied_facts(app):
    client,_=app
    first=manual(client,"Изучаю Python для личных задач","knowledge")
    manual(client,"Изучаю Python для проектов","knowledge")
    branches=client.get("/api/memory/tree").json()["branches"]
    node=next(x for x in branches if x["brain"]=="knowledge" and x["depth"]==1)
    assert MemoryEngine(_).branch_facts(node["id"],"main",cloud_mode=True)==[]
    assert first["id"] in {r["id"] for r in MemoryEngine(_).branch_facts(node["id"],"main",cloud_mode=False)}
    assert client.get("/api/memory/policy").json()["allow_cloud_embeddings"] is False


def test_auto_growth_can_be_paused_with_old_manual_review_mode(app):
    client,_=app
    assert client.put("/api/memory/policy",json={"auto_growth":False}).status_code==200
    say(client,"Я люблю шахматы")
    assert client.get("/api/memory/facts").json()["facts"]==[]
    candidates=client.get("/api/memory/candidates").json()["candidates"]
    assert len(candidates)==1
    assert client.post(
        "/api/memory/candidates/"+candidates[0]["id"]+"/review",json={"approve":True}
    ).status_code==200
    assert len(client.get("/api/memory/facts").json()["facts"])==1
    assert client.put("/api/memory/policy",json={"auto_growth":True}).status_code==200


def test_old_memory_is_indexed_in_branches_on_restart(app):
    client,path=app
    manual(client,"Изучаю Rust компилятор","knowledge")
    manual(client,"Изучаю Rust ассемблер","knowledge")
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("DELETE FROM memory_branch_members")
            conn.execute("DELETE FROM memory_branches WHERE depth>0")
    with TestClient(create_app(path)) as reopened:
        tree=reopened.get("/api/memory/tree").json()
        assert any(b["term"]=="rust" and b["depth"]==1 for b in tree["branches"])


def test_branch_data_cleared_when_conversation_erased(app):
    client,path=app
    say(client,"Я изучаю Rust compiler")
    say(client,"Я изучаю Rust assembler")
    assert any(x["term"]=="rust" for x in client.get("/api/memory/tree").json()["branches"])
    assert client.delete("/api/chat/messages").status_code==200
    assert client.get("/api/memory/facts").json()["facts"]==[]
    assert not any(x["depth"]>0 for x in client.get("/api/memory/tree").json()["branches"])
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_branch_members").fetchone()[0]==0



def test_safe_local_summaries_are_approved_without_interruption(app):
    client,_=app
    say(client,"Я изучаю Python")
    for i in range(5):
        say(client,"Простая реплика "+str(i))
    summaries=client.get("/api/memory/summaries").json()["summaries"]
    assert len(summaries)==1
    assert summaries[0]["status"]=="approved"
    assert summaries[0]["cloudAllowed"] is False
    assert "Python" in summaries[0]["content"]


def test_maintenance_prunes_expired_topic_branches(app):
    client,path=app
    first=manual(client,"Изучаю Kotlin инструменты","knowledge")
    manual(client,"Изучаю Kotlin документацию","knowledge")
    assert any(x["term"]=="kotlin" for x in client.get("/api/memory/tree").json()["branches"])
    client.put("/api/memory/facts/"+first["id"],json={
        "content":first["content"],"cloudAllowed":False,
        "revision":first["revision"],"expiresAt":1000,
    })
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("UPDATE memory_growth_maintenance SET last_run=0 WHERE id=1")
    client.post("/api/memory/process")
    assert not any(x["term"]=="kotlin" for x in client.get("/api/memory/tree").json()["branches"])


def test_topic_based_recall_still_respects_cloud_permissions(app):
    client,path=app
    first=manual(client,"Изучаю Python в проекте Rust","knowledge")
    manual(client,"Изучаю Python в проекте Scala","knowledge")
    engine=MemoryEngine(path)
    local=engine.recall("Объясни тему Python","main",False)
    assert any(x["id"]==first["id"] for x in local)
    assert engine.recall("Объясни тему Python","main",True)==[]
