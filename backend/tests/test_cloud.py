"""Cloud.ru: без реальной сети и без реального системного хранилища."""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud
from backend.app.main import create_app


@pytest.fixture
def vault(monkeypatch):
    secrets = {}
    monkeypatch.setattr(cloud.keyring, "get_password", lambda service, account: secrets.get((service, account)))
    monkeypatch.setattr(cloud.keyring, "set_password", lambda service, account, value: secrets.__setitem__((service, account), value))
    monkeypatch.setattr(cloud.keyring, "delete_password", lambda service, account: secrets.pop((service, account)))
    return secrets


@pytest.fixture
def client(tmp_path, vault):
    with TestClient(create_app(tmp_path / "test.sqlite3"), headers={"X-Meiyuren-Client": "1"}) as app:
        yield app


def local_headers():
    return {"Origin": "http://testserver"}


def test_secret_is_not_returned_and_model_is_persistent(client, tmp_path, vault):
    status = client.get("/api/cloud/settings").json()
    assert status["hasKey"] is False
    assert "key" not in status
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    status = client.get("/api/cloud/settings").json()
    assert status["hasKey"] is True
    assert "secret-test-123" not in str(status)
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/GigaChat3-10B-A1.8B", "enabled": True}, headers=local_headers()).status_code == 200
    with TestClient(create_app(tmp_path / "test.sqlite3")) as restarted:
        state = restarted.get("/api/cloud/settings").json()
        assert state["model"] == "ai-sage/GigaChat3-10B-A1.8B"
        assert state["enabled"] is True
    assert client.delete("/api/cloud/key", headers=local_headers()).status_code == 200
    assert client.get("/api/cloud/settings").json()["enabled"] is False
    assert vault == {}


def test_validation_and_origin(client):
    assert client.put("/api/cloud/key", json={"key": "12345678"}).status_code == 403
    assert client.put("/api/cloud/key", json={"key": "x"} , headers=local_headers()).status_code == 422
    assert client.put("/api/cloud/settings", json={"model": "one;rm -rf", "enabled": False}, headers=local_headers()).status_code == 422
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/model", "enabled": True}, headers=local_headers()).status_code == 409
    assert client.get("/api/cloud/models").status_code == 409


def test_missing_keyring_fails_closed(client, monkeypatch):
    def failed(*args):
        raise cloud.KeyringError("no backend")
    monkeypatch.setattr(cloud.keyring, "set_password", failed)
    response = client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers())
    assert response.status_code == 503
    assert "secret-test-123" not in str(response.json())


def test_cloud_models_and_chat_are_mocked(client, monkeypatch):
    calls = []

    async def fake_request(self, method_or_url, *args, **kwargs):
        url = str(method_or_url)
        # patched httpx only for known HTTP calls below
        calls.append((url, kwargs))
        if url.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "ai-sage/Test"}, {"id": "../invalid"}]}, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Облачный ответ"}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_request)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_request)
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    models = client.get("/api/cloud/models").json()["models"]
    assert models == ["ai-sage/Test"]
    assert client.put("/api/cloud/settings", json={"model": models[0], "enabled": True}, headers=local_headers()).status_code == 200
    result = client.post("/api/chat/messages", json={"text": "Привет", "requestId": "b2a034be-abcd-4bba-9caa-b4f20a293302"}).json()
    assert result["assistant"]["text"] == "Облачный ответ"
    assert len(calls) == 2
    assert "secret-test-123" not in str(result)


def test_auth_error_does_not_leak_key(client, monkeypatch):
    async def denied(self, url, *args, **kwargs):
        return httpx.Response(401, json={"detail": "secret-test-123"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", denied)
    client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers())
    r = client.get("/api/cloud/models")
    assert r.status_code == 401
    assert "secret-test-123" not in str(r.json())


def test_only_text_chat_models_are_offered(client, monkeypatch):
    async def fake_models(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"data": [
                {"id": "ai-sage/TextModel", "metadata": {"type": "chat"}},
                {"id": "Qwen/Qwen3-Embedding-0.6B", "metadata": {"type": "embedding"}},
                {"id": "some/reranker", "metadata": {"type": "text"}},
                {"id": "vendor/AudioAsr", "metadata": {"type": "audio"}},
                {"id": "vendor/no-metadata"},
                {"id": "../invalid"},
            ]},
            request=httpx.Request("GET", url),
        )
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_models)
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    models = client.get("/api/cloud/models").json()["models"]
    assert models == ["ai-sage/TextModel", "vendor/no-metadata"]


def test_context_budget_keeps_most_recent_turns():
    history = [
        {"role": "user" if i % 2 else "assistant", "text": str(i) + "x" * 2000}
        for i in range(20)
    ]
    result = cloud.bounded_context(history)
    assert 0 < len(result) <= 12
    assert sum(len(x["content"]) for x in result) <= cloud.MAX_CONTEXT_CHARS
    assert result[-1]["content"].startswith("19")
    assert all(x["role"] in {"user", "assistant"} for x in result)


def test_cloud_chat_payload_is_bounded_and_truncation_is_explained(client, monkeypatch):
    import asyncio

    captured = {}

    async def fake_chat(self, url, **kwargs):
        captured.update(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Частичный ответ"}, "finish_reason": "length"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_chat)
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    memory = "важная заметка " * 400
    turns = [{"role": "user" if i % 2 else "assistant", "text": "x" * 2000} for i in range(12)]
    answer = asyncio.run(cloud.generate_cloud_reply("ai-sage/Test", turns, memory, "Расскажи историю"))
    assert "Частичный ответ" in answer
    assert "обрезан" not in answer.lower()  # Сообщение об ограничении сформулировано понятным образом.
    assert "ограничением длины" in answer
    assert captured["max_tokens"] >= 1000
    assert sum(len(x["content"]) for x in captured["messages"][1:-1]) <= cloud.MAX_CONTEXT_CHARS
    assert len(captured["messages"][0]["content"]) <= 2200
    assert captured["messages"][-1] == {"role": "user", "content": "Расскажи историю"}


def test_cloud_errors_are_specific_and_no_secret_in_response(client, monkeypatch):
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    for status, expected in ((402, "оплат"), (404, "Модель"), (429, "частоту")):
        async def denied(self, url, **kwargs):
            return httpx.Response(status, json={"detail": "secret-test-123"}, request=httpx.Request("GET", url))
        monkeypatch.setattr(httpx.AsyncClient, "get", denied)
        response = client.get("/api/cloud/models")
        assert response.status_code == status
        assert expected.lower() in response.json()["detail"].lower()
        assert "secret-test-123" not in str(response.json())


def test_cloud_error_does_not_persist_failed_exchange(client, monkeypatch):
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=local_headers()).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/Test", "enabled": True}, headers=local_headers()).status_code == 200

    async def not_found(self, url, **kwargs):
        return httpx.Response(404, json={"detail": "not available"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", not_found)

    result = client.post("/api/chat/messages", json={"text": "Привет", "requestId": "29e25024-bf88-40ed-b7ad-24b8ed33c772"})
    assert result.status_code == 404
    assert "модель" in result.json()["detail"].lower()
    assert client.get("/api/chat/messages").json()["messages"] == []


def test_new_key_disables_previous_cloud_model(client):
    headers = local_headers()
    assert client.put("/api/cloud/key", json={"key": "first-secret-123"}, headers=headers).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/OldModel", "enabled": True}, headers=headers).status_code == 200
    changed = client.put("/api/cloud/key", json={"key": "second-secret-123"}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["enabled"] is False
    state = client.get("/api/cloud/settings").json()
    assert state["enabled"] is False
    assert state["model"] == "ai-sage/OldModel"
    assert state["hasKey"] is True
    assert client.get("/api/health").json()["engine"] == "demo"


def test_mutation_requires_client_header_and_proper_origin(client):
    assert client.post("/api/chat/messages", json={"text": "Hi"}, headers={"X-Meiyuren-Client": ""}).status_code == 403
    assert client.put("/api/memory", json={"notes": "test"}, headers={"X-Meiyuren-Client": ""}).status_code == 403
    assert client.delete("/api/chat/messages", headers={"X-Meiyuren-Client": ""}).status_code == 403
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers={
        "Origin": "http://evil.test",
        "X-Meiyuren-Client": "1",
    }).status_code == 403


def test_cloud_deduplicates_completed_requests_across_app_restart(client, monkeypatch, tmp_path):
    import uuid
    calls = []

    async def fake_post(self, url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Ответ Cloud"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    headers = local_headers()
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=headers).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/Test", "enabled": True}, headers=headers).status_code == 200
    request_id = str(uuid.uuid4())
    data = {"text": "Привет", "requestId": request_id}
    first = client.post("/api/chat/messages", json=data)
    second = client.post("/api/chat/messages", json=data)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json() == second.json()
    assert len(calls) == 1
    with TestClient(create_app(tmp_path / "test.sqlite3"), headers={"X-Meiyuren-Client": "1"}) as restored:
        third = restored.post("/api/chat/messages", json=data)
        assert third.status_code == 201
        assert third.json() == first.json()
        assert restored.get("/api/chat/messages").json()["messages"] == [first.json()["user"], first.json()["assistant"]]
    assert len(calls) == 1
    assert client.post("/api/chat/messages", json={"text": "Другое", "requestId": request_id}).status_code == 409


def test_failed_cloud_request_remains_reserved(client, monkeypatch):
    import uuid
    calls = []

    async def fail_post(self, url, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", fail_post)
    headers = local_headers()
    assert client.put("/api/cloud/key", json={"key": "secret-test-123"}, headers=headers).status_code == 200
    assert client.put("/api/cloud/settings", json={"model": "ai-sage/Test", "enabled": True}, headers=headers).status_code == 200
    data = {"text": "Привет", "requestId": str(uuid.uuid4())}
    response = client.post("/api/chat/messages", json=data)
    assert response.status_code == 504
    second = client.post("/api/chat/messages", json=data)
    assert second.status_code == 409
    assert len(calls) == 1
    assert client.get("/api/chat/messages").json()["messages"] == []


def test_bad_api_key_is_not_reflected_in_validation_response(client):
    secret = "short"
    response = client.put("/api/cloud/key", json={"key": secret}, headers=local_headers())
    assert response.status_code == 422
    assert secret not in str(response.json())
