"""Локальный FastAPI API: чат SQLite, память и Cloud.ru Foundation Models."""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import cloud, db
from .replies import generate_reply


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MemoryInput(BaseModel):
    notes: str = Field(max_length=4000)


class CloudKeyInput(BaseModel):
    key: str = Field(min_length=8, max_length=2048)


class CloudSettingsInput(BaseModel):
    model: str = Field(max_length=160)
    enabled: bool


def create_app(db_path: Path | None = None) -> FastAPI:
    database = db_path if db_path is not None else db.default_database()
    db.initialise(database)
    app = FastAPI(title="Meiyuren Local API", version="0.5.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def protect_cloud_settings(request: Request, call_next):
        if request.url.path.startswith("/api/cloud/") and request.method not in ("GET", "HEAD"):
            # Cross-site отправка ключа и смена модели должны быть запрещены.
            origin = request.headers.get("origin", "")
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.netloc != request.headers.get("host", "") or parsed.path:
                return JSONResponse({"detail": "Настройки доступны только из локального приложения."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/cloud/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(cloud.CloudError)
    async def cloud_error_handler(_request: Request, error: cloud.CloudError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.get("/api/health")
    def health() -> dict:
        settings = db.cloud_config(database)
        return {"status": "ok", "engine": "cloud" if settings["enabled"] else "demo", "storage": "sqlite"}

    @app.get("/api/chat/messages")
    def list_messages(limit: int = Query(default=100, ge=1, le=500)) -> dict:
        return {"messages": db.messages(database, limit)}

    @app.post("/api/chat/messages", status_code=201)
    async def send_message(body: ChatInput) -> dict:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
        notes = db.get_memory(database)["notes"]
        settings = db.cloud_config(database)
        if settings["enabled"]:
            # Только последние сообщения передаются облачному провайдеру.
            history = db.messages(database, limit=12)
            response = await cloud.generate_cloud_reply(settings["model"], history, notes, text)
        else:
            response = generate_reply(text, notes)
        # Ошибки провайдера не сохраняются как успешная переписка.
        return db.append_exchange(database, text, response)

    @app.delete("/api/chat/messages")
    def remove_messages() -> dict:
        return {"deleted": db.clear_messages(database)}

    @app.get("/api/memory")
    def read_memory() -> dict:
        return db.get_memory(database)

    @app.put("/api/memory")
    def save_memory(body: MemoryInput) -> dict:
        return db.put_memory(database, body.notes.strip())

    @app.get("/api/cloud/settings")
    def read_cloud_settings() -> dict:
        state = db.cloud_config(database)
        return {**state, "hasKey": bool(cloud.get_key())}

    @app.put("/api/cloud/key")
    def set_cloud_key(body: CloudKeyInput) -> dict:
        cloud.save_key(body.key)
        return {"hasKey": True}

    @app.delete("/api/cloud/key")
    def remove_cloud_key() -> dict:
        cloud.delete_key()
        current = db.cloud_config(database)
        db.update_cloud_config(database, current["model"], False)
        return {"hasKey": False, "enabled": False}

    @app.get("/api/cloud/models")
    async def read_cloud_models() -> dict:
        return {"models": await cloud.available_models()}

    @app.put("/api/cloud/settings")
    def set_cloud_settings(body: CloudSettingsInput) -> dict:
        if body.model and not cloud.valid_model(body.model):
            raise HTTPException(status_code=422, detail="Некорректный идентификатор модели.")
        if body.enabled and (not body.model or not cloud.get_key()):
            raise HTTPException(status_code=409, detail="Для включения Cloud.ru укажите модель и сохраните ключ.")
        return db.update_cloud_config(database, body.model, body.enabled)

    return app


app = create_app()
