"""Five brain long-term memory + explicit neural embeddings (no real Cloud.ru calls)."""
import uuid
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import BRAINS, EMBED_DIMS, EMBED_MODEL, MemoryEngine


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: "test-key-1234")
    path=tmp_path/"five-brains.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        yield client,path


def manual(app,text,brain=None,cloud_allowed=False):
    client,_=app
    response=client.post("/api/memory/facts",json={
        "content":text,"brain":brain,"cloudAllowed":cloud_allowed
    })
    assert response.status_code==201,response.text
    return response.json()


def test_five_brains_classify_and_persist(app):
    client,path=app
    items=[
        manual(app,"Я люблю кошек"),
        manual(app,"Вчера гулял в парке"),
        manual(app,"Хочу изучать Python"),
        manual(app,"Каждый день тренирую Python"),
        manual(app,"Изучаю Python")
    ]
    assert [x["brain"] for x in items]==list(BRAINS)
    status=client.get("/api/memory/brains")
    assert status.status_code==200
    assert all(status.json()["brains"][name]==1 for name in BRAINS)
    with TestClient(create_app(path)) as restarted:
        assert all(restarted.get("/api/memory/brains").json()["brains"][name]==1 for name in BRAINS)


def test_graph_links_related_brains_and_recall_expands(app):
    client,path=app
    one=manual(app,"Хочу изучать Python",brain="goals")
    two=manual(app,"Каждый день тренирую Python",brain="habits")
    assert client.get("/api/memory/brains").json()["links"]>=1
    network=client.get("/api/memory/brains/"+one["id"]+"/links")
    assert network.status_code==200
    assert any(n["item"]["id"]==two["id"] for n in network.json()["connections"])
    engine=MemoryEngine(path)
    result=engine.recall("изучать Python","main",False)
    assert {one["id"],two["id"]}.issubset({r["id"] for r in result})
    assert engine.recall("изучать Python","main",True)==[]


def test_brain_manually_changed_with_revision_and_backwards_compat(app):
    client,_=app
    item=manual(app,"Особенный проект",brain="knowledge")
    response=client.put("/api/memory/facts/"+item["id"],json={
        "content":item["content"],"revision":item["revision"],"cloudAllowed":False,
        "brain":"goals"
    })
    assert response.status_code==200
    assert response.json()["brain"]=="goals"
    assert client.post("/api/memory/facts",json={"content":"Hello","brain":"impossible"}).status_code==422


def test_no_automatic_paid_embedding_and_disallowed_content(app,monkeypatch):
    client,_=app
    item=manual(app,"Изучаю Python")
    calls=[]
    async def fake_post(self,url,**kwargs):
        calls.append(kwargs)
        raise AssertionError("Embeddings must never be called")
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_post)
    assert client.post("/api/memory/neural/index",json={
        "itemId":item["id"],"requestId":str(uuid.uuid4())
    }).status_code==409
    client.put("/api/memory/policy",json={"allow_cloud_embeddings":True})
    assert client.post("/api/memory/neural/index",json={
        "itemId":item["id"],"requestId":str(uuid.uuid4())
    }).status_code==409
    assert not calls
    assert client.post("/api/chat/messages",json={"text":"Привет"}).status_code==201
    assert not calls


def test_neural_embedding_and_search_only_with_explicit_consent(app,monkeypatch):
    client,path=app
    item=manual(app,"Изучаю Python",brain="knowledge",cloud_allowed=True)
    friend=manual(app,"Каждый день изучаю Python",brain="habits",cloud_allowed=True)
    assert client.put("/api/memory/policy",json={"allow_cloud_embeddings":True}).status_code==200
    calls=[]
    async def fake_post(self,url,**kwargs):
        calls.append(kwargs["json"])
        assert url.endswith("/embeddings")
        assert kwargs["json"]["model"]==EMBED_MODEL
        return httpx.Response(200,json={"data":[{"embedding":[1.0]+[0.0]*(EMBED_DIMS-1)}]},
                              request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_post)
    req=str(uuid.uuid4())
    assert client.post("/api/memory/neural/index",json={
        "itemId":item["id"],"requestId":req
    }).json()["status"]=="indexed"
    assert len(calls)==1
    result=client.post("/api/memory/neural/index",json={
        "itemId":item["id"],"requestId":str(uuid.uuid4())
    }).json()
    assert result["cached"] is True
    assert len(calls)==1
    # Same paid request ID cannot be reused on a different item.
    reused=client.post("/api/memory/neural/index",json={
        "itemId":friend["id"],"requestId":req
    })
    assert reused.status_code==409 and len(calls)==1
    assert client.post("/api/memory/neural/index",json={
        "itemId":friend["id"],"requestId":str(uuid.uuid4())
    }).status_code==200
    assert client.get("/api/memory/brains").json()["neuralVectors"]==2
    links=client.get("/api/memory/brains/"+item["id"]+"/links").json()["connections"]
    assert any(x["relation"]=="neural_similarity" and x["item"]["id"]==friend["id"] for x in links)
    search=client.post("/api/memory/neural/search",json={
        "q":"Учусь программировать","requestId":str(uuid.uuid4())})
    assert search.status_code==200,search.text
    matches=search.json()["matches"]
    assert len(matches)==2 and all(x["similarity"]>0.9 for x in matches)
    assert len(calls)==3
    assert client.delete("/api/memory/neural/vectors").json()["deleted"]==2
    assert client.get("/api/memory/brains").json()["neuralVectors"]==0


def test_revoked_permission_and_forgetting_remove_vectors(app,monkeypatch):
    client,path=app
    item=manual(app,"Люблю шахматы",cloud_allowed=True)
    client.put("/api/memory/policy",json={"allow_cloud_embeddings":True})
    async def fake_post(self,url,**kwargs):
        return httpx.Response(200,json={"data":[{"embedding":[1.0]+[0.0]*(EMBED_DIMS-1)}]},
                              request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_post)
    client.post("/api/memory/neural/index",json={
        "itemId":item["id"],"requestId":str(uuid.uuid4())})
    assert client.get("/api/memory/brains").json()["neuralVectors"]==1
    change=client.put("/api/memory/facts/"+item["id"],json={
        "content":item["content"],"revision":item["revision"],"cloudAllowed":False})
    assert change.status_code==200
    assert client.get("/api/memory/brains").json()["neuralVectors"]==0
    assert client.delete("/api/memory/facts/"+item["id"]).status_code==200
    with closing(db.connection(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]==0


def test_no_paid_retry_after_unknown_result(app,monkeypatch):
    client,path=app
    item=manual(app,"Изучаю алгоритмы",cloud_allowed=True)
    client.put("/api/memory/policy",json={"allow_cloud_embeddings":True})
    calls=[]
    async def fail(self,url,**kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("network stalled")
    monkeypatch.setattr(httpx.AsyncClient,"post",fail)
    request_id=str(uuid.uuid4())
    body={"itemId":item["id"],"requestId":request_id}
    first=client.post("/api/memory/neural/index",json=body)
    assert first.status_code==504
    second=client.post("/api/memory/neural/index",json=body)
    assert second.status_code==409 and len(calls)==1
    with closing(db.connection(path)) as conn:
        status=conn.execute(
            "SELECT status FROM memory_embedding_requests WHERE request_id=?",(request_id,)
        ).fetchone()[0]
    assert status=="unknown"


def test_neural_search_secrets_and_cross_site_mutation_blocked(app):
    client,_=app
    client.put("/api/memory/policy",json={"allow_cloud_embeddings":True})
    denied=client.post("/api/memory/neural/search",json={
        "q":"my api key secret", "requestId":str(uuid.uuid4())})
    assert denied.status_code==409
    cross_site=client.post("/api/memory/neural/index",json={
        "itemId":"not-real","requestId":str(uuid.uuid4())
    },headers={"X-Meiyuren-Client":""})
    assert cross_site.status_code==403
