from fastapi.testclient import TestClient
from backend.app.main import create_app

def test_quality_gate_requires_real_user_feedback(tmp_path):
    with TestClient(create_app(tmp_path/"quality.sqlite3")) as client:
        response=client.get("/api/memory/universe/quality-gate")
        assert response.status_code==200,response.text
        quality=response.json()
        assert quality["cases"]==0
        assert quality["sufficientEvidence"] is False
        assert quality["activeScore"] is None
        assert quality["baselineScore"] is None
        assert quality["deltaVsBaseline"] is None
        assert quality["scores"]=={}
        assert quality["generalIntelligenceMeasured"] is False
        assert quality["holdoutIndependent"] is False
        assert "content" not in response.text
