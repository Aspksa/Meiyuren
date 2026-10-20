"""Cloud.ru model capabilities and streaming resilience: all mocked, no paid calls."""
import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import cloud
from backend.app.main import create_app


def test_compatibility_requires_positive_metadata():
    vague = cloud.evaluate_compatibility("vendor/chat", {"id": "vendor/chat"})
    assert vague["status"] == "unknown"
    assert vague["checkedWithoutGeneration"] is True
    assert vague["warnings"]

    confirmed = cloud.evaluate_compatibility("vendor/chat", {
        "id": "vendor/chat",
        "max_model_len": 16000,
        "supports_streaming": True,
        "metadata": {"supported_parameters": ["temperature", "max_tokens"]},
    })
    assert confirmed["status"] == "compatible"
    assert confirmed["issues"] == []
    assert confirmed["maxModelLen"] == 16000


@pytest.mark.parametrize("entry,reason", [
    ({"id": "vendor/embedding-v1"}, "не текстовая"),
    ({"id": "vendor/chat", "supports_streaming": False}, "streaming"),
    ({"id": "vendor/chat", "max_model_len": 1000}, "контекста"),
    ({"id": "vendor/chat", "supported_parameters": ["temperature", "max_completion_tokens"]}, "max_tokens"),
])
def test_compatibility_rejects_explicit_conflicts(entry, reason):
    result = cloud.evaluate_compatibility(entry["id"], entry)
    assert result["status"] == "incompatible"
    assert reason.lower() in " ".join(result["issues"]).lower()


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: "mock-secret")


def test_compatibility_endpoint_no_chat_calls(tmp_path, monkeypatch, fake_key):
    async def get_models(self, url, **kwargs):
        assert url.endswith("/models")
        return httpx.Response(200, json={"data": [
            {"id": "vendor/chat", "max_model_len": 16000},
            {"id": "vendor/embedding-v1", "metadata": {"type": "embedding"}},
        ]}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", get_models)
    with TestClient(create_app(tmp_path / "compat.sqlite3")) as client:
        valid = client.get("/api/cloud/compatibility?model=vendor%2Fchat")
        assert valid.status_code == 200
        assert valid.json()["status"] == "unknown"
        denied = client.get("/api/cloud/compatibility?model=vendor%2Fembedding-v1")
        assert denied.json()["status"] == "incompatible"
        missing = client.get("/api/cloud/compatibility?model=vendor%2Fnotfound")
        assert missing.json()["status"] == "incompatible"
        assert client.get("/api/cloud/compatibility?model=bad%20model").status_code == 422


class FakeResponse:
    def __init__(self, lines, failure=None):
        self.lines = lines
        self.failure = failure

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line
        if self.failure:
            raise self.failure


def install_stream(monkeypatch, lines, failure=None):
    requests = []

    @asynccontextmanager
    async def fake_stream(self, method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/chat/completions")
        assert kwargs["json"]["stream"] is True
        requests.append(kwargs["json"])
        yield FakeResponse(lines, failure)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    return requests


def run_stream():
    async def fetch():
        return [part async for part in cloud.stream_cloud_reply("vendor/chat", [], "", "Привет")]
    return asyncio.run(fetch())


def payload(text, finish_reason=None):
    return "data: " + json.dumps({"choices": [
        {"delta": {"content": text}, "finish_reason": finish_reason}
    ]})


def test_stream_accepts_complete_sse(monkeypatch, fake_key):
    calls = install_stream(monkeypatch, [
        ': heartbeat', payload("Привет"), "",
        'data: {"choices":[],"usage":{"completion_tokens":2}}',
        payload(", мир!", "stop"), "data: [DONE]",
    ])
    assert "".join(run_stream()) == "Привет, мир!"
    assert len(calls) == 1


@pytest.mark.parametrize("lines,fragment", [
    ([payload("Часть")], "без [DONE]"),
    (["data: {bad json"], "повреждённое"),
    (["data: [DONE]"], "без текстового"),
    ([payload("   "), "data: [DONE]"], "без текстового"),
    (["data: " + json.dumps({"error": {"message": "SECRET"}})], "ошибке внутри SSE"),
    ([payload("X" * 8001), "data: [DONE]"], "8000 символов"),
    (["data: " + "x" * 65537], "слишком большое"),
])
def test_stream_rejects_broken_empty_or_oversized_sse(monkeypatch, fake_key, lines, fragment):
    calls = install_stream(monkeypatch, lines)
    with pytest.raises(cloud.CloudError) as raised:
        run_stream()
    assert fragment.lower() in str(raised.value).lower()
    assert "SECRET" not in str(raised.value)
    assert len(calls) == 1


def test_read_timeout_blocks_retries(monkeypatch, fake_key):
    calls = install_stream(monkeypatch, [payload("Часть")], httpx.ReadTimeout("read stalled"))
    with pytest.raises(cloud.CloudError) as raised:
        run_stream()
    assert raised.value.status == 504
    assert "60 секунд" in str(raised.value)
    assert len(calls) == 1


def test_http_status_errors_keep_meaning(monkeypatch, fake_key):
    @asynccontextmanager
    async def denied(self, method, url, **kwargs):
        class Unauthorized:
            def raise_for_status(self):
                req = httpx.Request("POST", url)
                raise httpx.HTTPStatusError("401 SECRET", request=req, response=httpx.Response(401, request=req))
        yield Unauthorized()
    monkeypatch.setattr(httpx.AsyncClient, "stream", denied)
    with pytest.raises(cloud.CloudError) as raised:
        run_stream()
    assert raised.value.status == 401
    assert "SECRET" not in str(raised.value)
