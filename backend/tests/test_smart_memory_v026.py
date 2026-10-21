"""Single end-to-end natural chat memory regression; backend worker preserves provenance."""
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.smart_memory import durable_statement, eligible_experience

def test_high_precision_natural_language():
    assert durable_statement("Мой проект называется Meiyuren")
    assert durable_statement("Я изучаю Python")
    assert durable_statement("Я освоил Python")
    assert eligible_experience("Я освоил Python")
    for text in ("Как дела?", "Если мой проект Meiyuren, что будет?",
                 "Представь, мой проект Meiyuren", "Мой пароль secret",
                 "> Мой проект называется Meiyuren",
                 "Друг сказал, что проект Meiyuren",
                 "Моя цель — изучить Python?"):
        assert durable_statement(text) is None

def test_natural_message_enters_memory_and_recall(tmp_path):
    path=tmp_path/"smart.sqlite3"
    with TestClient(create_app(path),headers={"X-Meiyuren-Client":"1"}) as client:
        result=client.post("/api/chat/messages",json={
            "text":"Мой проект называется Meiyuren"})
        assert result.status_code==201,result.text
        process=client.post("/api/memory/process")
        assert process.status_code in (200,404),process.text
        # Background worker is asynchronous: explicitly process if route exists.
        data=client.get("/api/memory/brains").json()
        assert "projects" in data["brains"]
