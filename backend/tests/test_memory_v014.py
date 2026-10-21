"""Autonomous eight-brain neuroevolution: stable migrations, consent, rollback."""
from contextlib import closing
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine, BRAINS


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring,"get_password",lambda *_:None)
    path=tmp_path/"evolution.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        yield client,path


def manual(client,text,brain="knowledge",cloud_allowed=False):
    response=client.post("/api/memory/facts",json={
        "content":text,"brain":brain,"cloudAllowed":cloud_allowed
    })
    assert response.status_code==201,response.text
    return response.json()


def test_default_autonomous_policy_and_all_eight_existing_brains(app):
    client,path=app
    policy=client.get("/api/memory/policy").json()
    assert policy["auto_evolution"] and policy["auto_growth"]
    assert policy["auto_extract"] and policy["auto_summaries"]
    assert policy["allow_cloud_embeddings"] is False
    assert policy["allow_cloud_facts"] is False
    net=client.get("/api/memory/brains").json()
    assert set(net["brains"])==set(BRAINS)
    status=client.get("/api/memory/evolution").json()
    assert status["strategy"]=="balanced"
    assert status["automatic"] is True
    assert status["generation"]>=1
    assert status["adaptiveSynapses"]==0


def test_microbrains_grow_and_are_pruned_from_confirmed_sources(app):
    client,path=app
    facts=[
        manual(client,"Изучаю Python FastAPI SQLite"),
        manual(client,"Изучаю Python FastAPI сервер"),
        manual(client,"Изучаю Python FastAPI HTTP"),
        manual(client,"Изучаю Python Django тестирование"),
        manual(client,"Изучаю Kotlin разработку"),
    ]
    status=client.get("/api/memory/evolution").json()
    assert status["microbrains"]>=1
    with closing(db.connection(path)) as conn:
        rows=conn.execute(
            "SELECT m.id,m.branch_id,m.root_brain,b.depth,b.support "
            "FROM memory_microbrains m JOIN memory_branches b ON b.id=m.branch_id"
        ).fetchall()
        assert rows and all(r["depth"]>=2 and r["support"]>=3 for r in rows)
        assert all(r["root_brain"]=="knowledge" for r in rows)
    assert client.delete("/api/memory/facts/"+facts[0]["id"]).status_code==200
    assert client.delete("/api/memory/facts/"+facts[1]["id"]).status_code==200
    with closing(db.connection(path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_microbrains m "
            "LEFT JOIN memory_branches b ON b.id=m.branch_id WHERE b.id IS NULL"
        ).fetchone()[0]==0
        assert conn.execute(
            "SELECT COUNT(*) FROM memory_branch_members WHERE memory_id IN (?,?)",
            (facts[0]["id"],facts[1]["id"])
        ).fetchone()[0]==0


def test_evolution_replay_bounded_no_llm_calls_and_deterministic_fallback(app,monkeypatch):
    client,path=app
    called=[]
    async def deny_network(*_args,**_kwargs):
        called.append(1)
        raise AssertionError("Evolution must never call Cloud.ru")
    monkeypatch.setattr(httpx.AsyncClient,"post",deny_network)
    for i in range(14):
        manual(client,"Изучаю Python направление "+str(i))
    result=client.post("/api/memory/evolution/evaluate")
    assert result.status_code==200,result.text
    evolution=result.json()
    assert evolution["generation"]>=2
    assert evolution["strategy"] in ("balanced","focused","context")
    assert not called
    with closing(db.connection(path)) as conn:
        rows=conn.execute(
            "SELECT strategy,selected,benchmark_cases,proxy_score "
            "FROM memory_evolution_trials WHERE generation=?",(evolution["generation"],)
        ).fetchall()
        assert len(rows)==3
        assert sum(r["selected"] for r in rows)==1
        assert all(0<=r["proxy_score"]<=1 for r in rows)
        assert all(r["benchmark_cases"]<=80 for r in rows)
    result=client.post("/api/memory/evolution/reset")
    assert result.status_code==200
    assert result.json()["strategy"]=="balanced"
    assert len(client.get("/api/memory/facts").json()["facts"])==14


def test_synaptic_plasticity_only_on_explicit_feedback(app):
    client,path=app
    one=manual(client,"Изучаю Python FastAPI HTTP","knowledge")
    two=manual(client,"Изучаю Python FastAPI SQLite","knowledge")
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_synaptic_weights").fetchone()[0]==0
    helpful=client.post("/api/memory/deep/facts/"+one["id"]+"/feedback",json={"helpful":True})
    assert helpful.status_code==200,helpful.text
    with closing(db.connection(path)) as conn:
        row=conn.execute("SELECT adjustment,observations FROM memory_synaptic_weights").fetchone()
    assert row and row["adjustment"]==pytest.approx(0.04)
    assert row["observations"]==1
    for _ in range(20):
        client.post("/api/memory/deep/facts/"+one["id"]+"/feedback",json={"helpful":True})
    with closing(db.connection(path)) as conn:
        weight=conn.execute("SELECT adjustment FROM memory_synaptic_weights").fetchone()[0]
    assert weight<=0.4
    client.post("/api/memory/deep/facts/"+one["id"]+"/feedback",json={"helpful":False})
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT adjustment FROM memory_synaptic_weights").fetchone()[0]<weight
    assert client.get("/api/memory/facts").json()["facts"][0]["status"]=="confirmed"


def test_private_sources_never_released_by_neural_evolution(app):
    client,path=app
    secret=manual(client,"Изучаю Python приватная идея","knowledge")
    shared=manual(client,"Изучаю Python открытые технологии","knowledge",True)
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    client.post("/api/memory/deep/facts/"+secret["id"]+"/feedback",json={"helpful":True})
    client.post("/api/memory/evolution/evaluate")
    result=MemoryEngine(path).deep_recall("Python","main",True)
    assert {r["id"] for r in result}=={shared["id"]}
    assert secret["content"] not in client.get("/api/memory/recall",params={
        "q":"Python","cloudMode":True
    }).json()["context"]


def test_edit_and_forget_remove_derived_synaptic_weights(app):
    client,path=app
    a=manual(client,"Изучаю Python FastAPI SQL")
    manual(client,"Изучаю Python FastAPI сервер")
    client.post("/api/memory/deep/facts/"+a["id"]+"/feedback",json={"helpful":True})
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_synaptic_weights").fetchone()[0]>=1
    edit=client.put("/api/memory/facts/"+a["id"],json={
        "content":"Изучаю машинное обучение", "revision":a["revision"],
        "brain":"knowledge","cloudAllowed":False
    })
    assert edit.status_code==200,edit.text
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_synaptic_weights WHERE left_id=? OR right_id=?",
                            (a["id"],a["id"])).fetchone()[0]==0
    assert client.delete("/api/memory/facts/"+a["id"]).status_code==200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_synaptic_weights WHERE left_id=? OR right_id=?",
                            (a["id"],a["id"])).fetchone()[0]==0
    client.post("/api/memory/evolution/evaluate")
    assert a["id"] not in {r["id"] for r in client.get("/api/memory/facts").json()["facts"]}


def test_evolution_can_be_paused_without_affecting_memory(app):
    client,path=app
    item=manual(client,"Изучаю Python FastAPI")
    before=client.get("/api/memory/evolution").json()
    assert client.put("/api/memory/policy",json={"auto_evolution":False}).status_code==200
    engine=MemoryEngine(path)
    state=engine.evolve()
    assert state["automatic"] is False
    assert state["generation"]==before["generation"]
    assert client.post("/api/memory/process").status_code==200
    assert engine.evolution_status()["generation"]==before["generation"]
    assert client.get("/api/memory/facts").json()["facts"][0]["id"]==item["id"]


def test_automatic_restart_migration_is_idempotent(app):
    client,path=app
    item=manual(client,"Изучаю Python FastAPI")
    first=client.get("/api/memory/evolution").json()["generation"]
    with TestClient(create_app(path)) as reopened:
        second=reopened.get("/api/memory/evolution").json()
        assert second["generation"]==first
        assert item["id"] in {r["id"] for r in reopened.get("/api/memory/facts").json()["facts"]}
        assert second["strategy"] in ("balanced","focused","context")
