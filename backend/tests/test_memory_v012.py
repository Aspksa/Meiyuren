"""v0.12: eight-brain deep memory correctness, privacy, continuation and performance."""
from contextlib import closing
from time import perf_counter
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import BRAINS, MemoryEngine


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    path = tmp_path / "deep.sqlite3"
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as client:
        yield client, path


def fact(client, content, brain, allowed=False):
    resp = client.post("/api/memory/facts", json={
        "content":content, "brain":brain, "cloudAllowed":allowed
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_deep_migration_preserves_all_eight_brains_and_metadata(api):
    client,path=api
    ids=[]
    for brain in BRAINS:
        ids.append(fact(client, "Я помню заметку "+brain,brain)["id"])
    overview=client.get("/api/memory/deep/overview").json()
    assert overview["count"] == 8
    assert {b["brain"] for b in overview["brains"]} == set(BRAINS)
    assert all(b["count"] == 1 for b in overview["brains"])
    assert len(overview["timeline"]) == 8
    with TestClient(create_app(path)) as fresh:
        assert fresh.get("/api/memory/deep/overview").json()["count"] == 8
        assert {x["id"] for x in fresh.get("/api/memory/facts").json()["facts"]} == set(ids)
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_deep_events").fetchone()[0]==8


def test_projects_goals_decisions_explicit_state_only(api):
    client,_=api
    project=fact(client,"Я разрабатываю проект Meiyuren", "projects")
    paused=fact(client,"Я отложил проект тестирования", "projects")
    done=fact(client,"Я завершил проект обучения", "projects")
    no_claim=fact(client,"Проект Meiyuren", "projects")
    decision=fact(client,"Я решил использовать Python, потому что это проще", "decisions")
    overview=client.get("/api/memory/deep/overview").json()
    states={r["id"]:r["eventState"] for r in overview["timeline"]}
    assert states[project["id"]]=="active"
    assert states[paused["id"]]=="paused"
    assert states[done["id"]]=="completed"
    assert states[no_claim["id"]]=="unspecified"
    assert done["id"] not in {r["id"] for r in overview["continuation"]}
    assert decision["id"] in {r["id"] for r in overview["decisions"]}
    reason=next(r["statedReason"] for r in overview["decisions"] if r["id"]==decision["id"])
    assert reason=="это проще"
    assert next(r["statedReason"] for r in overview["timeline"] if r["id"]==project["id"]) is None


def test_continue_where_left_off_combines_projects_goals_and_decisions(api):
    client,path=api
    project=fact(client,"Разрабатываю Meiyuren интерфейс","projects")
    goal=fact(client,"Планирую улучшить SQLite поиск","goals")
    decision=fact(client,"Я решил использовать FastAPI","decisions")
    fact(client,"У меня есть кошка по кличке Туча","identity")
    preview=client.get("/api/memory/recall",params={
        "q":"Продолжим там где остановились", "conversationId":"main", "cloudMode":False
    })
    assert preview.status_code==200,preview.text
    ids={r["id"] for r in preview.json()["memories"]}
    assert {project["id"],goal["id"],decision["id"]} <= ids
    assert "Meiyuren" in preview.json()["context"]
    engine=MemoryEngine(path)
    route=engine._route_brains("Давай продолжим проект")
    assert "projects" in route


def test_deep_cloud_policy_blocks_local_notes_and_records(api):
    client,_=api
    private=fact(client,"Я разрабатываю Python секретный проект", "projects")
    public=fact(client,"Я изучаю TypeScript", "knowledge", True)
    cloud_overview=client.get("/api/memory/deep/overview",params={
        "conversationId":"main","cloudMode":True
    }).json()
    assert cloud_overview["count"]==0
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    cloud_overview=client.get("/api/memory/deep/overview",params={
        "conversationId":"main","cloudMode":True
    }).json()
    assert cloud_overview["count"]==1
    assert {x["id"] for x in cloud_overview["timeline"]}=={public["id"]}
    assert private["id"] not in {x["id"] for x in cloud_overview["continuation"]}
    preview=client.get("/api/memory/recall",params={
        "q":"Продолжим проект Python","cloudMode":True
    }).json()
    assert private["content"] not in preview["context"]


def test_deep_feedback_affects_rank_not_truth_and_no_duplicate_raw_queries(api):
    client,path=api
    item=fact(client,"Я хочу программировать Python","goals")
    before=client.get("/api/memory/deep/overview").json()
    assert before["count"]==1
    r=client.post("/api/memory/deep/facts/"+item["id"]+"/feedback",json={"helpful":True})
    assert r.status_code==200 and r.json()["helpful"]==1
    r=client.post("/api/memory/deep/facts/"+item["id"]+"/feedback",json={"helpful":False})
    assert r.status_code==200 and r.json()["unhelpful"]==1
    item_after=client.get("/api/memory/facts").json()["facts"][0]
    assert item_after["status"]=="confirmed"
    first=client.get("/api/memory/recall",params={"q":"Python"})
    assert first.status_code==200
    metrics=client.get("/api/memory/deep/metrics").json()
    assert metrics["indexedEvents"]==1
    # preview must not log or mutate metrics.
    assert metrics["search"]==[]
    MemoryEngine(path).prepare("Python","main",False)
    metrics=client.get("/api/memory/deep/metrics").json()
    assert sum(m["searches"] for m in metrics["search"])==1
    with closing(db.connection(path)) as conn:
        cols={row["name"] for row in conn.execute("PRAGMA table_info(memory_deep_telemetry)")}
        assert "query" not in cols and "content" not in cols


def test_deletion_and_revision_do_not_resurrect_derived_events_or_outline(api):
    client,path=api
    item=fact(client,"Я разрабатываю Meiyuren","projects")
    engine=MemoryEngine(path)
    assert engine.deep_overview("main")["count"]==1
    updated=client.put("/api/memory/facts/"+item["id"],json={
        "content":"Я завершил проект Meiyuren","brain":"projects",
        "revision":item["revision"],"cloudAllowed":False,
    })
    assert updated.status_code==200,updated.text
    assert engine.deep_overview("main")["timeline"][0]["eventState"]=="completed"
    assert client.delete("/api/memory/facts/"+item["id"]).status_code==200
    assert engine.deep_overview("main")["count"]==0
    client.post("/api/memory/deep/rebuild")
    with closing(db.connection(path)) as conn:
        for table,key in [("memory_deep_events","memory_id"),("memory_deep_feedback","memory_id")]:
            assert conn.execute("SELECT COUNT(*) FROM "+table+" WHERE "+key+"=?",
                                (item["id"],)).fetchone()[0]==0
        rows=conn.execute("SELECT item_ids FROM memory_deep_outline").fetchall()
        assert not any(item["id"] in row["item_ids"] for row in rows)


def test_clearing_conversation_removes_deep_items_not_global_user_facts(api):
    client,_=api
    global_item=fact(client,"Я изучаю SQL","knowledge")
    exchange=client.post("/api/chat/messages",json={"text":"Я разрабатываю Rust проект"})
    assert exchange.status_code==201
    client.post("/api/memory/process")
    before=client.get("/api/memory/deep/overview").json()
    assert before["count"]==2
    assert client.delete("/api/chat/messages").status_code==200
    after=client.get("/api/memory/deep/overview").json()
    assert after["count"]==1
    assert after["timeline"][0]["id"]==global_item["id"]


def test_deep_multi_hop_never_includes_forbidden_memory(api):
    client,path=api
    a=fact(client,"Проект Python связанный с SQLite","projects",True)
    fact(client,"Изучаю SQLite для проекта FastAPI","knowledge",True)
    private=fact(client,"Изучаю FastAPI только локально","knowledge",False)
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    engine=MemoryEngine(path)
    cloud=engine.deep_recall("Проект Python", "main",True,max_items=12)
    assert all(r["cloudAllowed"] for r in cloud)
    assert private["id"] not in {r["id"] for r in cloud}
    assert a["id"] in {r["id"] for r in cloud}


def test_deep_offline_performance_on_bounded_legacy_fixture(tmp_path):
    from backend.app import history
    path=tmp_path/"benchmark.sqlite3"
    db.initialise(path)
    history.initialise(path)
    engine=MemoryEngine(path)
    engine.initialize()
    # Fill fixture transactionally; avoid N individual API/index rebuild calls.
    with closing(db.connection(path)) as conn:
        with conn:
            for n in range(320):
                content="Изучаю Python модуль "+str(n)
                conn.execute(
                    "INSERT INTO memory_items "
                    "(id,content,fingerprint,kind,status,cloud_allowed,created_at,updated_at,brain) "
                    "VALUES(?,?,?,'manual','confirmed',0,?,?,?)",
                    ("bulk-"+str(n),content, "hash-"+str(n), 1000+n, 1000+n, "knowledge")
                )
                conn.execute("INSERT INTO memory_fts(item_id,content) VALUES(?,?)",
                             ("bulk-"+str(n),content))
    start=perf_counter()
    assert engine.rebuild_deep_index()["indexed"]==320
    for _ in range(12):
        result=engine.deep_recall("Изучаю Python модуль 15","main",False)
        assert result
    assert perf_counter()-start<25  # CI safety threshold, not a product latency claim
