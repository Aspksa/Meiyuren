"""OMEGA live API honors Memory Core visibility."""
from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_omega_empty_local_database(tmp_path):
    with TestClient(create_app(tmp_path/"omega.sqlite3")) as client:
        response=client.get("/api/memory/omega/overview")
        assert response.status_code==200
        overview=response.json()
        assert overview["immuneSystem"]["accepted"]==0
        assert overview["neuroFactory"]["subbrains"]==0
        assert overview["selfEngineering"]["automaticCodeExecution"] is False
        assert overview["limitations"]["remoteFederation"] is False
