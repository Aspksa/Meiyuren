"""v0.21 source-safe background maintenance regression."""
from contextlib import closing
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.neural_operations import NeuralOperations
from backend.app.neural_synapses import SynapticStore
from backend.app import db, cloud


def test_maintenance_never_drops_valid_source_and_drops_orphans(tmp_path):
    path=tmp_path/"test.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        client.post("/api/chat/messages",json={"text":"Hello world"})
        with closing(db.connection(path)) as conn:
            source=conn.execute("SELECT id FROM messages LIMIT 1").fetchone()[0]
            with conn:
                conn.execute("""INSERT INTO memory_items
                    (id,content,fingerprint,kind,status,source_message_id,conversation_id,
                    cloud_allowed,created_at,updated_at)
                    VALUES ('valid','Example','fp','fact','confirmed',?,'main',0,1,1)""",(source,))
        store=SynapticStore(path)
        # Put an orphan and an eligible pair into the index; the orphan is removed.
        store.feedback("valid","missing",True,eligible={"valid","missing"})
        operations=NeuralOperations(path)
        result=operations.tick(force=True)
        assert result["ran"] and result["purged"]==1
        assert "valid" in operations._eligible()
        assert operations.tick()["reason"]=="interval"


def test_protected_operations_api(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud.keyring,"get_password",lambda *_:None)
    with TestClient(create_app(tmp_path/"api.sqlite3")) as client:
        result=client.get("/api/neural/operations")
        assert result.status_code==200
        assert result.json()["externalCalls"] is False
        assert client.post("/api/neural/operations/consolidate").status_code==403
        assert client.post("/api/neural/operations/consolidate",
                           headers={"X-Meiyuren-Client":"1"}).status_code==200
