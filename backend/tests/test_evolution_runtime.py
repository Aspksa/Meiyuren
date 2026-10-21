"""Regression coverage for opt-in autonomous evolution runtime."""
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app import cognitive_evolution as lab
from backend.app.evolution_runtime import EvolutionRuntime


def test_evolution_default_off_and_no_fixtures(tmp_path):
    runtime = EvolutionRuntime(tmp_path / "lab.sqlite3")
    assert runtime.status()["automaticEvaluationEnabled"] is False
    assert runtime.tick()["reason"] == "disabled"
    assert runtime.tick(manual=True)["reason"] == "insufficient_independent_fixtures"
    assert runtime.set_enabled(True)["automaticEvaluationEnabled"] is True
    assert runtime.tick()["reason"] == "insufficient_independent_fixtures"


def test_evaluation_requires_fixture_threshold_and_respects_interval(tmp_path):
    runtime = EvolutionRuntime(tmp_path / "lab.sqlite3")
    with runtime._db() as db:
        for i in range(8):
            item = lab.Evidence("projects", f"project {i} knowledge",
                f"project {i} fact", f"local:case-{i}",
                "2026-10-21T00:00:00Z")
            identifier = lab.register_evidence(db, item)
            lab.register_fixture(db, f"project {i}", identifier,
                                 "train" if i < 3 else "holdout")
    runtime.set_enabled(True)
    result = runtime.tick()
    assert result["ran"] is True
    assert runtime.tick()["reason"] == "interval"
    assert runtime.status()["lastEvaluationAt"] is not None


def test_api_routes_are_protected_and_read_only_status(tmp_path, monkeypatch):
    from backend.app import cloud
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    with TestClient(create_app(tmp_path / "app.sqlite3")) as client:
        status = client.get("/api/evolution/status")
        assert status.status_code == 200
        assert status.json()["automaticEvaluationEnabled"] is False
        assert client.post("/api/evolution/automatic?enabled=true").status_code == 403
        assert client.post("/api/evolution/automatic?enabled=true",
                           headers={"X-Meiyuren-Client": "1"}).status_code == 200
        assert client.post("/api/evolution/evaluate",
                           headers={"X-Meiyuren-Client": "1"}).json()["ran"] is False
