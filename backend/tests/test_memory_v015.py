"""v0.15 Cortex Mesh: evidence, ACLs, provenance, forgetting and bounded replay."""
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import BRAINS, MemoryEngine


@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud.keyring,"get_password",lambda *_:None)
    path=tmp_path/"cortex.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        yield client,path


def fact(client,content,brain,cloud_allowed=False):
    r=client.post("/api/memory/facts",json={
        "content":content,"brain":brain,"cloudAllowed":cloud_allowed
    })
    assert r.status_code==201,r.text
    return r.json()


def say(client,text,conversation="main"):
    r=client.post("/api/chat/messages",json={"text":text,"conversationId":conversation})
    assert r.status_code==201,r.text
    assert client.post("/api/memory/process").status_code==200
    return r.json()


def test_cortex_connects_distinct_brains_using_two_shared_source_terms(app):
    client,path=app
    project=fact(client,"Разрабатываю Meiyuren Python SQLite","projects")
    knowledge=fact(client,"Изучаю Meiyuren Python SQLite","knowledge")
    decision=fact(client,"Решил Meiyuren Python SQLite","decisions")
    c=client.get("/api/memory/cortex")
    assert c.status_code==200
    payload=c.json()
    assert payload["roots"]==8
    assert payload["edges"]>=2
    assert payload["connectedBrains"]>=3
    assert len(BRAINS)==8
    result=client.get("/api/memory/cortex/facts/"+project["id"]+"/connections")
    assert result.status_code==200
    edges=result.json()["connections"]
    assert {e["item"]["id"] for e in edges}>={knowledge["id"],decision["id"]}
    assert all(e["fromBrain"]=="projects" and
               e["toBrain"] in ("knowledge","decisions") and
               e["sharedTerms"]>=2 and e["relation"]=="shared_evidence" for e in edges)
    with closing(db.connection(path)) as conn:
        raw=conn.execute("SELECT * FROM memory_cortex_edges").fetchall()
    assert raw
    assert all("content" not in row.keys() for row in raw)


def test_no_one_word_false_cortex_connections_and_deterministic_rebuild(app):
    client,_=app
    fact(client,"Изучаю Python Gears","knowledge")
    fact(client,"Мой проект Python Rust","projects")
    assert client.get("/api/memory/cortex").json()["edges"]==0
    fact(client,"Я решил применять Python Gears","decisions")
    before=client.get("/api/memory/cortex").json()["edges"]
    assert before>=1
    for _ in range(2):
        r=client.post("/api/memory/cortex/rebuild")
        assert r.status_code==200 and r.json()["cortexEdges"]==before
    assert client.get("/api/memory/cortex").json()["edges"]==before


def test_cross_brain_recall_reaches_linked_other_brain(app):
    client,path=app
    project=fact(client,"Разрабатываю Meiyuren Python SQLite","projects")
    knowledge=fact(client,"Изучаю Meiyuren Python SQLite","knowledge")
    engine=MemoryEngine(path)
    found=engine.deep_recall("Разрабатываю Meiyuren","main",False,max_items=2)
    assert {project["id"],knowledge["id"]}<={item["id"] for item in found}
    assert all(item["status"]=="confirmed" for item in found)


def test_cortex_acl_blocks_private_items_and_disabled_cloud(app):
    client,path=app
    private=fact(client,"Разрабатываю Meiyuren Python SQLite","projects")
    shared=fact(client,"Изучаю Meiyuren Python SQLite","knowledge",True)
    assert client.get("/api/memory/cortex/facts/"+shared["id"]+"/connections",params={
        "cloudMode":True
    }).json()["connections"]==[]
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    assert client.get("/api/memory/cortex").json()["edges"]>=1
    assert client.get("/api/memory/cortex/facts/"+shared["id"]+"/connections",params={
        "cloudMode":True
    }).json()["connections"]==[]
    cloud_items=MemoryEngine(path).deep_recall("Meiyuren Python","main",True)
    assert private["id"] not in {row["id"] for row in cloud_items}
    assert private["content"] not in client.get("/api/memory/recall",params={
        "q":"Meiyuren Python","cloudMode":True
    }).json()["context"]


def test_cortex_no_scope_links_across_unrelated_conversations(app):
    client,path=app
    one=client.post("/api/conversations",json={"title":"Одна работа"})
    two=client.post("/api/conversations",json={"title":"Другая работа"})
    assert one.status_code==two.status_code==201
    a=one.json()["id"];b=two.json()["id"]
    say(client,"Я разрабатываю проект Meiyuren Python",a)
    say(client,"Я изучаю проект Meiyuren Python",b)
    with closing(db.connection(path)) as conn:
        raw=conn.execute("SELECT * FROM memory_cortex_edges").fetchall()
    assert raw==[]
    assert client.get("/api/memory/cortex",params={"conversationId":a}).json()["provenance"]["confirmed"]==1
    assert client.get("/api/memory/cortex",params={"conversationId":b}).json()["provenance"]["confirmed"]==1
    ids=[r["id"] for r in client.get("/api/memory/facts").json()["facts"]]
    assert len(ids)==2
    assert client.get("/api/memory/cortex/facts/"+ids[0]+"/connections",params={
        "conversationId":b
    }).json()["connections"]==[]


def test_evidence_coverage_separates_confirmed_fact_from_available_message_source(app):
    client,_=app
    fact(client,"Изучаю SQL FastAPI","knowledge")
    said=say(client,"Я изучаю Python Meiyuren")
    report=client.get("/api/memory/cortex").json()["provenance"]
    assert report["confirmed"]==2
    assert report["sourceBacked"]==1
    assert report["withoutMessageSource"]==1
    assert report["potentialPreferenceConflicts"]>=0
    assert said["user"]["id"]


def test_deleted_expired_and_changed_facts_cannot_survive_mesh(app):
    client,path=app
    project=fact(client,"Разрабатываю Meiyuren Python SQLite","projects")
    knowledge=fact(client,"Изучаю Meiyuren Python SQLite","knowledge")
    assert client.get("/api/memory/cortex").json()["edges"]>=1
    edited=client.put("/api/memory/facts/"+project["id"],json={
        "content":"Разрабатываю независимую программу",
        "brain":"projects","revision":project["revision"],"cloudAllowed":False
    })
    assert edited.status_code==200
    assert client.get("/api/memory/cortex").json()["edges"]==0
    assert client.delete("/api/memory/facts/"+knowledge["id"]).status_code==200
    assert client.post("/api/memory/cortex/rebuild").status_code==200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_cortex_edges").fetchone()[0]==0
    assert client.get("/api/memory/cortex/facts/"+knowledge["id"]+"/connections").json()["connections"]==[]


def test_synaptic_feedback_enhances_mesh_and_forgetting_prunes_weights(app):
    client,path=app
    project=fact(client,"Разрабатываю Meiyuren Python SQLite","projects")
    knowledge=fact(client,"Изучаю Meiyuren Python SQLite","knowledge")
    assert client.post("/api/memory/deep/facts/"+project["id"]+"/feedback",
                       json={"helpful":True}).status_code==200
    with closing(db.connection(path)) as conn:
        first=conn.execute("SELECT adjustment FROM memory_synaptic_weights "
                           "WHERE left_id=? OR right_id=?",(project["id"],project["id"])).fetchone()
    assert first is not None and first["adjustment"]>0
    assert client.delete("/api/memory/facts/"+project["id"]).status_code==200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_synaptic_weights "
                            "WHERE left_id=? OR right_id=?",
                            (project["id"],project["id"])).fetchone()[0]==0


def test_cortex_benchmark_uses_no_cloud_and_changes_no_facts(app,monkeypatch):
    client,path=app
    calls=[]
    async def deny_network(*_args,**_kwargs):
        calls.append(1)
        raise AssertionError("Cortex benchmark must stay entirely offline")
    monkeypatch.setattr(httpx.AsyncClient,"post",deny_network)
    for i in range(18):
        fact(client,f"Изучаю Python SQLite направление {i}","knowledge" if i%2==0 else "projects")
    old_ids={item["id"] for item in client.get("/api/memory/facts").json()["facts"]}
    run=client.post("/api/memory/cortex/evaluate")
    assert run.status_code==200,run.text
    score=run.json()
    assert 0<=score["baselineHits"]<=score["cases"]<=32
    assert 0<=score["meshHits"]<=score["cases"]
    status=client.get("/api/memory/cortex").json()
    assert status["evaluation"]["cases"]==score["cases"]
    assert {item["id"] for item in client.get("/api/memory/facts").json()["facts"]}==old_ids
    assert calls==[]
    with closing(db.connection(path)) as conn:
        columns={r["name"] for r in conn.execute("PRAGMA table_info(memory_cortex_benchmarks)")}
    assert "query" not in columns and "content" not in columns


def test_old_v014_facts_migrate_without_reclassifying(app):
    client,path=app
    person=fact(client,"Я изучаю Python SQLite","identity")
    project=fact(client,"Я разрабатываю Python SQLite","projects")
    with TestClient(create_app(path)) as reopened:
        assert reopened.get("/api/memory/cortex").json()["roots"]==8
        items={item["id"]:item for item in reopened.get("/api/memory/facts").json()["facts"]}
        assert items[person["id"]]["brain"]=="identity"
        assert items[project["id"]]["brain"]=="projects"
        assert reopened.get("/api/memory/cortex").json()["edges"]>=1
