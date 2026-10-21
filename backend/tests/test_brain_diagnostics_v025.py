"""Runtime brain diagnostics must be grounded in backend counters, never LLM role-play."""
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.brain_diagnostics import is_diagnostic_request, diagnostic_report

def test_diagnostic_intent():
    assert is_diagnostic_request("Проведи самодиагностику всех 8 мозгов")
    assert is_diagnostic_request("Проверь состояние мозга и памяти")
    assert not is_diagnostic_request("Запомни: мой проект Meiyuren")

def test_eight_brains_report_grounded_empty():
    report=diagnostic_report({"network":{"brains":{"identity":0},"links":0,
             "neuralVectors":0},"facts":0,"cortex":{"edges":0},
             "evolution":{"evaluations":6}})
    assert "identity: подтверждённых записей 0" in report
    assert "knowledge: подтверждённых записей 0" in report
    assert "Эволюционные оценки: 6" in report
    assert "восьми независимых LLM" in report

def test_normal_chat_diagnostic_uses_backend(tmp_path):
    with TestClient(create_app(tmp_path/"brain_diagnostics.sqlite3")) as client:
        result=client.post("/api/chat/messages",json={
            "text":"Проведи самодиагностику всех 8 мозгов"} )
        assert result.status_code==201, result.text
        answer=result.json()["assistant"]["text"]
        assert "identity: подтверждённых записей 0" in answer
        assert "Связи памяти: 0" in answer
        assert "системные метрики" in answer.lower()

def test_stream_chat_diagnostic_uses_backend(tmp_path):
    with TestClient(create_app(tmp_path/"brain_stream.sqlite3")) as client:
        response=client.post("/api/chat/stream",json={
            "text":"Проверка восьми мозгов: статус памяти"})
        assert response.status_code==200
        assert "event: done" in response.text
        assert "identity: подтверждённых записей 0" in response.text
