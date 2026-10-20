"""Локальный FastAPI API: чат SQLite, память и Cloud.ru Foundation Models."""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import cloud, db
from .replies import generate_reply


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    requestId: str | None = Field(default=None, max_length=40)


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
        protected_path = request.url.path.startswith(("/api/cloud/", "/api/chat/", "/api/memory"))
        if protected_path and request.method not in ("GET", "HEAD", "OPTIONS"):
            # Для всех изменений нужен нестандартный заголовок и проверка Origin.
            # Сторонний веб-сайт не может отправить этот заголовок без CORS-разрешения.
            if request.headers.get("x-meiyuren-client") != "1":
                return JSONResponse({"detail": "Требуется запрос из локального приложения."}, status_code=403)
            # Cross-site отправка ключа и смена модели должны быть запрещены.
            origin = request.headers.get("origin", "")
            parsed = urlsplit(origin)
            if (request.url.path.startswith("/api/cloud/") and not origin) or (origin and (parsed.scheme != "http" or parsed.netloc != request.headers.get("host", "") or parsed.path)):
                return JSONResponse({"detail": "Настройки доступны только из локального приложения."}, status_code=403)
        response = await call_next(request)
        if protected_path:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError):
        if request.url.path == "/api/cloud/key":
            # Pydantic может включить исходный ввод в 422. Не возвращаем API-ключ обратно.
            return JSONResponse({"detail": "Некорректный формат ключа Cloud.ru."}, status_code=422)
        return JSONResponse({"detail": error.errors()}, status_code=422)

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
            if not body.requestId:
                raise HTTPException(status_code=422, detail="Для Cloud.ru требуется идентификатор запроса.")
            # Вставка уникального requestId в SQLite ДО платного запроса.
            state, existing = db.reserve_request(database, body.requestId, text)
            if state == "done":
                return existing
            if state != "new":
                raise HTTPException(
                    status_code=409,
                    detail="Этот запрос уже был отправлен в Cloud.ru. Результат неизвестен или запрос ещё выполняется. "
                           "Повторная платная отправка заблокирована. Дождитесь ответа или явно создайте новый запрос.",
                )
            history = db.messages(database, limit=12)
            try:
                response = await cloud.generate_cloud_reply(settings["model"], history, notes, text)
                return db.finish_request(database, body.requestId, text, response)
            except Exception:
                # Сохраняем резервирование: повтор с тем же ID не создаст второй платный вызов.
                db.fail_request(database, body.requestId)
                raise
        response = generate_reply(text, notes)
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
        # Новый ключ может иметь другие права / модели. Всегда выключаем прежний Cloud-режим.
        previous = db.cloud_config(database)
        db.update_cloud_config(database, previous["model"], False)
        return {"hasKey": True, "enabled": False}

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
