"""Memory Core v0.8: stale answers, forgotten information, reconciliation and retrieval."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db, history
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    with TestClient(create_app(tmp_path / "memory-v08.sqlite3"),
                    headers={"X-Meiyuren-Client": "1"}) as app:
        yield app


def say(client, message):
    response = client.post("/api/chat/messages", json={"text": message})
    assert response.status_code == 201, response.text
    return response.json()


def review_candidate(client):
    client.post("/api/memory/process")
    candidates = client.get("/api/memory/candidates").json()["candidates"]
    assert candidates
    return candidates[0]


def test_old_response_cannot_resurrect_cleared_history(client, tmp_path):
    path = tmp_path / "memory-v08.sqlite3"
    epoch = history.conversation_epoch(path, "main")
    reserved, _ = db.reserve_request(path, "1cd54d90-467a-4dbb-87e9-934eed1b4c42", "Hello")
    assert reserved == "new"
    history.mark_cloud_conversation(path, "1cd54d90-467a-4dbb-87e9-934eed1b4c42", "main")
    assert client.delete("/api/chat/messages").status_code == 200
    assert history.conversation_epoch(path, "main") == epoch + 1
    with pytest.raises(history.StaleConversation):
        history.complete_cloud_exchange(path,"1cd54d90-467a-4dbb-87e9-934eed1b4c42",
                                        "main","Hello","Late answer",epoch)
    assert client.get("/api/chat/messages").json()["messages"] == []


def test_lexical_russian_morphology_and_privacy(client,tmp_path):
    item = client.post("/api/memory/facts",json={
        "content":"Я люблю шахматы","cloudAllowed":True}).json()
    path=tmp_path/"memory-v08.sqlite3"
    engine=MemoryEngine(path)
    assert item["id"] in [m["id"] for m in engine.recall("С кем играть в шахматами?", "main",False)]
    assert not engine.recall("С кем играть в шахматами?", "main",True)
    client.put("/api/memory/policy",json={"allow_cloud_facts":True})
    matched=engine.recall("Играть в шахматах", "main",True)
    assert len(matched)==1 and matched[0]["id"]==item["id"]
    result=client.get("/api/memory/recall",params={
        "q":"Играть в шахматах","conversationId":"main","cloudMode":True})
    assert result.status_code==200
    assert item["id"] in [m["id"] for m in result.json()["memories"]]
    assert engine.prepare("Играть в шахматах","main",True)
    usage=client.get("/api/memory/usage").json()["entries"]
    assert usage and usage[0]["memoryId"]==item["id"]


def test_approval_reconciles_explicitly_opposite_preferences(client,tmp_path):
    say(client,"Я люблю кофе")
    first=review_candidate(client)
    client.post("/api/memory/candidates/"+first["id"]+"/review",json={"approve":True})
    original=client.get("/api/memory/facts").json()["facts"][0]
    say(client,"Я больше не люблю кофе")
    second=review_candidate(client)
    assert second["conflictWith"]==original["id"]
    client.post("/api/memory/candidates/"+second["id"]+"/review",json={"approve":True})
    facts=client.get("/api/memory/facts").json()["facts"]
    assert len(facts)==1 and "не люблю кофе" in facts[0]["content"]
    path=tmp_path/"memory-v08.sqlite3"
    with closing(db.connection(path)) as conn:
        previous=conn.execute("SELECT status,superseded_by FROM memory_items WHERE id=?",
                              (original["id"],)).fetchone()
    assert previous["status"]=="superseded"
    assert previous["superseded_by"]==facts[0]["id"]
    assert len(MemoryEngine(path).recall("люблю кофе","main",False))==1


def test_edit_has_revision_log_and_expiration(client,tmp_path):
    original=client.post("/api/memory/facts",json={"content":"Люблю шахматы"}).json()
    new=client.put("/api/memory/facts/"+original["id"],json={
        "content":"Предпочитаю шахматы","revision":original["revision"],
        "cloudAllowed":False,"expiresAt":1000
    })
    assert new.status_code==200,new.text
    assert new.json()["revision"]==2
    assert MemoryEngine(tmp_path/"memory-v08.sqlite3").recall("шахматами","main",False)==[]
    explanation=client.get("/api/memory/facts/"+original["id"]+"/explain").json()
    assert [r["revision"] for r in explanation["revisions"]]==[2,1]
    assert explanation["revisions"][0]["content"]=="Предпочитаю шахматы"
    assert explanation["revisions"][1]["content"]=="Люблю шахматы"
    assert client.delete("/api/memory/facts/"+original["id"]).status_code==200
    with closing(db.connection(tmp_path/"memory-v08.sqlite3")) as conn:
        assert conn.execute("SELECT 1 FROM memory_revisions WHERE memory_id=?",
                            (original["id"],)).fetchone() is None


def test_forgotten_source_cannot_resurface_in_summaries(client,tmp_path):
    say(client,"Я люблю шахматы")
    first=review_candidate(client)
    assert client.post("/api/memory/candidates/"+first["id"]+"/review",
                       json={"approve":True}).status_code==200
    for i in range(5):
        say(client,"Обычная реплика номер "+str(i))
    client.post("/api/memory/process")
    summary=client.get("/api/memory/summaries").json()["summaries"]
    assert len(summary)==1 and "шахматы" in summary[0]["content"]
    item=client.get("/api/memory/facts").json()["facts"][0]
    assert client.delete("/api/memory/facts/"+item["id"]).status_code==200
    assert client.get("/api/memory/summaries").json()["summaries"]==[]
    for i in range(6,12):
        say(client,"Обычная реплика номер "+str(i))
    client.post("/api/memory/process")
    assert client.get("/api/memory/summaries").json()["summaries"]==[]
    assert client.get("/api/memory/candidates").json()["candidates"]==[]


def test_no_raw_transcript_summaries_without_confirmed_facts(client):
    for i in range(6):
        say(client,"Только личный текст "+str(i))
    client.post("/api/memory/process")
    assert client.get("/api/memory/summaries").json()["summaries"]==[]


def test_summary_queue_is_coalesced(client,tmp_path):
    for i in range(13):
        say(client,"Простая реплика "+str(i))
    with closing(db.connection(tmp_path/"memory-v08.sqlite3")) as conn:
        total=conn.execute("SELECT COUNT(*) FROM memory_jobs WHERE kind='summary'").fetchone()[0]
    assert total<=2  # вместо 13 повторяющихся задач


def test_backup_precedes_memory_migration(tmp_path):
    path=tmp_path/"existing.sqlite3"
    db.initialise(path)
    history.initialise(path)
    history.add_fact(path,"Люблю код")
    with TestClient(create_app(path)) as app:
        assert app.get("/api/memory/status").status_code==200
    backup=path.with_name(path.name+".before-memory-core.bak")
    assert backup.exists()
    with closing(db.connection(backup)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='memory_items'").fetchone() is None
        old=conn.execute("SELECT content FROM memory_facts").fetchall()
        assert [row["content"] for row in old]==["Люблю код"]



def test_forgetting_current_preference_cascades_to_superseded_versions(client, tmp_path):
    say(client, "Я люблю кофе")
    first=review_candidate(client)
    client.post("/api/memory/candidates/"+first["id"]+"/review",json={"approve":True})
    say(client, "Я больше не люблю кофе")
    next_candidate=review_candidate(client)
    client.post("/api/memory/candidates/"+next_candidate["id"]+"/review",json={"approve":True})
    current=client.get("/api/memory/facts").json()["facts"][0]
    assert client.delete("/api/memory/facts/"+current["id"]).status_code==200
    with closing(db.connection(tmp_path/"memory-v08.sqlite3")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM memory_revisions").fetchone()[0]==0
    assert client.get("/api/memory/facts").json()["facts"]==[]


def test_migration_drops_untrusted_raw_v07_summaries(tmp_path):
    path=tmp_path/"from-v07.sqlite3"
    db.initialise(path)
    history.initialise(path)
    engine=MemoryEngine(path)
    engine.initialize()
    with closing(db.connection(path)) as conn:
        with conn:
            conn.execute("DELETE FROM memory_revisions")
            conn.execute("DROP TABLE memory_revisions")
            conn.execute(
                "INSERT INTO memory_summaries(conversation_id,content,source_message_id,"
                "status,cloud_allowed,updated_at) VALUES(?,?,?,?,?,?)",
                ("main","Старая копия сырых сообщений","legacy-id","approved",1,123)
            )
    with TestClient(create_app(path)) as app:
        assert app.get("/api/memory/summaries").json()["summaries"]==[]
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_summaries").fetchone()[0]==0
