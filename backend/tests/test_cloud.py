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
    with TestClient(create_app(tmp_path / "test.sqlite3")) as app:
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
    result = client.post("/api/chat/messages", json={"text": "Привет"}).json()
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
