"""Neural Universe graph exposes provenance metadata without private memory texts."""
from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_neural_universe_graph_is_empty_and_private(tmp_path):
    with TestClient(create_app(tmp_path/"universe.sqlite3")) as client:
        response=client.get("/api/memory/universe/graph")
        assert response.status_code==200
        data=response.json()
        assert data["nodes"]==[]
        assert data["edges"]==[]
        assert data["events"]==[]
        assert data["privateContentExposed"] is False
        assert data["source"]=="local_sqlite"
        assert client.get("/api/memory/universe/graph?limit=9999").status_code==422
