from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_evolution_lab_is_bounded_private_and_backed_by_sqlite(tmp_path):
    with TestClient(create_app(tmp_path/"evolution.sqlite3")) as client:
        r=client.get("/api/memory/universe/evolution-lab")
        assert r.status_code==200,r.text
        data=r.json()
        assert len(data["branchesByBrain"])==8
        assert data["trials"]==[]
        assert data["readOnly"] is True
        assert data["evolution"]["strategy"] in {"balanced","focused","context"}
        assert "content" not in r.text
        assert "private" not in r.text
