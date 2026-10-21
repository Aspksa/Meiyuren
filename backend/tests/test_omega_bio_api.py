from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_live_adaptive_overview_never_promotes(tmp_path):
    with TestClient(create_app(tmp_path/"brain.sqlite3")) as client:
        response=client.get("/api/memory/adaptive/overview")
        assert response.status_code==200
        data=response.json()
        assert data["experts"]==0
        assert data["activeTopologyUnchanged"] is True
        assert data["sourceScoped"] is True
