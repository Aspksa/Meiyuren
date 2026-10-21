from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_integrity_and_aggregate_snapshots(tmp_path):
    with TestClient(create_app(tmp_path/"universe.sqlite3")) as client:
        result=client.get("/api/memory/universe/health")
        assert result.status_code==200
        health=result.json()
        assert health["healthy"] is True
        assert health["orphanLinks"] == 0
        assert health["orphanVectors"] == 0
        assert len(health["brains"])==8
        sample=client.get("/api/memory/universe/snapshots")
        assert sample.status_code==200
        snapshot=sample.json()
        assert snapshot["aggregateOnly"] is True
        assert len(snapshot["snapshots"])==1
        assert snapshot["snapshots"][0]["brains"]==health["brains"]
        assert "content" not in sample.text
        assert "memory_id" not in sample.text
