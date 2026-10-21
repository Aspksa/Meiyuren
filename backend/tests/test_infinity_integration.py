"""Live Infinity Growth cannot read memories outside visibility policy."""
from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_infinity_overview_live_endpoint(tmp_path):
    with TestClient(create_app(tmp_path / "growth.sqlite3")) as client:
        response=client.get("/api/memory/infinity/overview")
        assert response.status_code==200
        data=response.json()
        assert data["mode"]=="read_only_proposal"
        assert data["memories"]==0
        assert data["remoteExecution"] is False
        assert sum(data["localShardCounts"].values())==0
