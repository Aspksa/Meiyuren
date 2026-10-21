"""v0.13: source-grounded episodic memory, checkpoints, privacy and long history."""
from contextlib import closing
from datetime import datetime, timezone
from time import perf_counter
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, history
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine


@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud.keyring,"get_password",lambda *_: None)
    path=tmp_path/"episodic.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        yield client,path


def say(client,text,conversation="main"):
    response=client.post("/api/chat/messages",json={
        "text":text,"conversationId":conversation
    })
    assert response.status_code==201,response.text
    processed=client.post("/api/memory/process")
    assert processed.status_code==200,processed.text
    return response.json()


def manual(client,text,brain="projects",allowed=False):
    r=client.post("/api/memory/facts",json={
        "content":text,"brain":brain,"cloudAllowed":allowed
    })
    assert r.status_code==201,r.text
    return r.json()


def test_episode_groups_source_verified_facts_by_observation_date(app):
    client,path=app
    a=say(client,"Я разрабатываю проект Meiyuren")
    b=say(client,"Я изучаю SQLite")
    result=client.get("/api/memory/episodes")
    assert result.status_code==200,result.text
    overview=result.json()
    assert overview["count"]==1
    episode=overview["episodes"][0]
    assert episode["conversationId"]=="main"
    assert {x["sourceMessageId"] for x in episode["facts"]}=={
        a["user"]["id"], b["user"]["id"]
    }
    assert all("user" not in x["content"].casefold() for x in episode["facts"])
    assert episode["day"]==datetime.fromtimestamp(
        episode["observedStart"]/1000,timezone.utc
    ).date().isoformat()
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_episode_members").fetchone()[0]==2


def test_explicit_event_day_never_confused_with_observation_time(app):
    client,_=app
    a=manual(client,"Я завершил проект Meiyuren 2025-03-14")
    b=manual(client,"Я начал проект Meiyuren 14.03.2025")
    c=manual(client,"Я начал проект Meiyuren 32.03.2025")
    out=client.get("/api/memory/episodes").json()
    dates={x["memoryId"]:x["eventDay"] for x in out["explicitEventDates"]}
    assert dates[a["id"]]=="2025-03-14"
    assert dates[b["id"]]=="2025-03-14"
    assert c["id"] not in dates
    assert out["count"]==0  # Manual notes are not fabricated as chat episodes.


def test_project_checkpoints_are_explicit_and_latest_completion_wins(app):
    client,_=app
    active=manual(client,"Я разрабатываю проект Meiyuren")
    paused=manual(client,"Я отложил проект Meiyuren")
    done=manual(client,"Я завершил проект Meiyuren")
    overview=client.get("/api/memory/episodes").json()
    grouped=[x for x in overview["checkpoints"] if x["projectKey"]=="project:meiyuren"]
    assert {x["state"] for x in grouped}=={"active","paused","completed"}
    assert done["id"] in {x["memoryId"] for x in grouped}
    assert "project:meiyuren" not in {x["projectKey"] for x in overview["continuation"]}
    recall=client.get("/api/memory/recall",params={
        "q":"Продолжим проект Meiyuren","cloudMode":False
    })
    assert recall.status_code==200


def test_latest_paused_checkpoint_available_for_continuation(app):
    client,_=app
    manual(client,"Я разрабатываю проект Meiyuren")
    last=manual(client,"Я отложил проект Meiyuren")
    out=client.get("/api/memory/episodes").json()
    item=next(x for x in out["continuation"] if x["projectKey"]=="project:meiyuren")
    assert item["memoryId"]==last["id"]
    assert item["state"]=="paused"
    preview=client.get("/api/memory/recall",params={
        "q":"Продолжим там где остановились","cloudMode":False
    }).json()
    assert last["content"] in preview["context"]


def test_anonymous_project_does_not_share_checkpoint_with_named_project(app):
    client,_=app
    first=manual(client,"Я разрабатываю новую версию приложения")
    named=manual(client,"Я завершил проект Meiyuren")
    out=client.get("/api/memory/episodes").json()
    keys={x["memoryId"]:x["projectKey"] for x in out["checkpoints"]}
    assert keys[first["id"]]!=keys[named["id"]]


def test_local_cloud_permissions_apply_to_episode_and_checkpoint_context(app):
    client,_=app
    private=say(client,"Я разрабатываю проект ТолькоЛокально")
    public=manual(client,"Я разрабатываю проект PublicApp","projects",True)
    assert client.get("/api/memory/episodes",params={"cloudMode":True}).json()["count"]==0
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    out=client.get("/api/memory/episodes",params={"cloudMode":True}).json()
    assert not out["episodes"]
    assert {x["memoryId"] for x in out["checkpoints"]}=={public["id"]}
    text=client.get("/api/memory/recall",params={
        "q":"Продолжим проект","cloudMode":True
    }).json()["context"]
    assert "ТолькоЛокально" not in text
    assert private["user"]["id"] not in str(out)


def test_forgetting_and_clearing_prune_episode_members_and_checkpoints(app):
    client,path=app
    say(client,"Я разрабатываю проект Meiyuren")
    say(client,"Я изучаю Python")
    out=client.get("/api/memory/episodes").json()
    assert out["count"]==1
    fact=next(x for x in client.get("/api/memory/facts").json()["facts"]
              if "Meiyuren" in x["content"])
    assert client.delete("/api/memory/facts/"+fact["id"]).status_code==200
    assert all(fact["id"] not in {x["id"] for x in episode["facts"]}
               for episode in client.get("/api/memory/episodes").json()["episodes"])
    assert all(fact["id"]!=point["memoryId"]
               for point in client.get("/api/memory/episodes").json()["checkpoints"])
    assert client.delete("/api/chat/messages").status_code==200
    data=client.get("/api/memory/episodes").json()
    assert data["count"]==0 and data["checkpoints"]==[]
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_episode_members").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM memory_project_checkpoints").fetchone()[0]==0


def test_episode_isolated_by_conversation_id(app):
    client,_=app
    create=client.post("/api/conversations",json={"title":"Второй проект"})
    assert create.status_code==201,create.text
    conversation=create.json()["id"]
    say(client,"Я изучаю Python",conversation)
    say(client,"Я изучаю Rust","main")
    second=client.get("/api/memory/episodes",params={"conversationId":conversation}).json()
    first=client.get("/api/memory/episodes",params={"conversationId":"main"}).json()
    assert second["count"]==first["count"]==1
    assert "Rust" not in str(second)
    assert "Python" not in str(first)


def test_episode_rebuild_idempotent_and_restarts_preserve_source_links(app):
    client,path=app
    say(client,"Я разрабатываю проект Meiyuren")
    before=client.get("/api/memory/episodes").json()
    rebuild=client.post("/api/memory/episodes/rebuild")
    assert rebuild.status_code==200
    after=client.get("/api/memory/episodes").json()
    assert [x["id"] for x in before["episodes"]]==[x["id"] for x in after["episodes"]]
    with TestClient(create_app(path)) as reopened:
        assert reopened.get("/api/memory/episodes").json()["count"]==1


def test_long_history_10000_messages_source_grounded_and_bounded(tmp_path):
    path=tmp_path/"long-history.sqlite3"
    db.initialise(path)
    history.initialise(path)
    engine=MemoryEngine(path)
    engine.initialize()
    base=1720000000000
    with closing(db.connection(path)) as conn:
        with conn:
            for i in range(10000):
                message_id="msg-"+str(i)
                conn.execute(
                    "INSERT INTO messages(id,role,text,sent_at,conversation_id) VALUES(?,?,?,?,?)",
                    (message_id,"user" if i%2==0 else "assistant",
                     "Длинная история "+str(i),base+i*90000,"main")
                )
            for i in range(0,2400,2):
                memory_id="memory-"+str(i)
                content="Я изучаю SQL часть "+str(i)
                conn.execute(
                    "INSERT INTO memory_items"
                    "(id,content,fingerprint,kind,status,source_message_id,"
                    "conversation_id,cloud_allowed,created_at,updated_at,brain) "
                    "VALUES(?,?,?,'auto','confirmed',?,'main',0,?,?, 'knowledge')",
                    (memory_id,content,"fingerprint-"+str(i),"msg-"+str(i),
                     base+i*90000,base+i*90000)
                )
                conn.execute(
                    "INSERT INTO memory_fts(item_id,content) VALUES(?,?)",
                    (memory_id,content)
                )
    start=perf_counter()
    indexed=engine.rebuild_deep_index()
    assert indexed["indexed"]==1200
    assert indexed["episodes"]>=2
    view=engine.episode_overview("main")
    assert view["count"]>=2
    assert engine.deep_recall("Изучаю SQL часть 22","main",False)
    assert perf_counter()-start<45  # CI regression guard, not production SLA.
