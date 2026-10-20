"""Локальный FastAPI API: чат SQLite, память и Cloud.ru Foundation Models."""
from pathlib import Path
import asyncio
import json
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import cloud, db, history
from .replies import generate_reply


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    requestId: str | None = Field(default=None, max_length=40)
    conversationId: str = Field(default="main", max_length=40)


class MemoryInput(BaseModel):
    notes: str = Field(max_length=4000)


class ConversationInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class FactInput(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class CloudKeyInput(BaseModel):
    key: str = Field(min_length=8, max_length=2048)


class CloudSettingsInput(BaseModel):
    model: str = Field(max_length=160)
    enabled: bool


def create_app(db_path: Path | None = None) -> FastAPI:
    database = db_path if db_path is not None else db.default_database()
    db.initialise(database)
    history.initialise(database)
    app = FastAPI(title="Meiyuren Local API", version="0.6.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def protect_cloud_settings(request: Request, call_next):
        protected_path = request.url.path.startswith(("/api/cloud/", "/api/chat/", "/api/memory", "/api/conversations"))
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

    def require_conversation(conv_id: str) -> None:
        if not history.ensure_conversation(database, conv_id):
            raise HTTPException(status_code=404, detail="Диалог не найден.")

    def memory_context() -> str:
        notes = db.get_memory(database)["notes"]
        facts = history.list_facts(database)
        if facts:
            notes += "\\nСохранённые вручную факты:\\n" + "\\n".join(
                "- " + fact["content"] for fact in facts[:20]
            )
        return notes

    @app.get("/api/chat/messages")
    def list_messages(
        limit: int = Query(default=100, ge=1, le=500),
        conversationId: str = Query(default="main", max_length=40),
    ) -> dict:
        require_conversation(conversationId)
        return {"messages": history.messages(database, conversationId, limit)}

    @app.post("/api/chat/messages", status_code=201)
    async def send_message(body: ChatInput) -> dict:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
        require_conversation(body.conversationId)
        notes = memory_context()
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
            history.mark_cloud_conversation(database, body.requestId, body.conversationId)
            previous = history.messages(database, body.conversationId, limit=12)
            try:
                response = await cloud.generate_cloud_reply(settings["model"], previous, notes, text)
                return history.complete_cloud_exchange(database, body.requestId, body.conversationId, text, response)
            except Exception:
                # Сохраняем резервирование: повтор с тем же ID не создаст второй платный вызов.
                db.fail_request(database, body.requestId)
                raise
        response = generate_reply(text, notes)
        return history.append_exchange(database, text, response, body.conversationId)

    @app.delete("/api/chat/messages")
    def remove_messages(conversationId: str = Query(default="main", max_length=40)) -> dict:
        require_conversation(conversationId)
        return {"deleted": history.clear_messages(database, conversationId)}

    @app.post("/api/chat/stream")
    async def stream_message(body: ChatInput):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, detail="Сообщение не может быть пустым.")
        require_conversation(body.conversationId)
        settings = db.cloud_config(database)
        if settings["enabled"] and not body.requestId:
            raise HTTPException(422, detail="Для Cloud.ru требуется идентификатор запроса.")

        def event(name, data):
            return "event: " + name + "\\ndata: " + json.dumps(data, ensure_ascii=False) + "\\n\\n"

        async def stream():
            reserved = False
            completed = False
            try:
                if not settings["enabled"]:
                    result = history.append_exchange(
                        database, text, generate_reply(text, memory_context()), body.conversationId)
                    yield event("delta", {"text": result["assistant"]["text"]})
                    yield event("done", result)
                    return
                state, existing = db.reserve_request(database, body.requestId, text)
                if state == "done":
                    yield event("done", existing)
                    return
                if state != "new":
                    yield event("error", {"message": "Запрос уже отправлен или его статус неизвестен. "
                        "Повторная платная отправка заблокирована."})
                    return
                reserved = True
                history.mark_cloud_conversation(database, body.requestId, body.conversationId)
                previous = history.messages(database, body.conversationId, limit=12)
                tokens = []
                async for piece in cloud.stream_cloud_reply(
                    settings["model"], previous, memory_context(), text
                ):
                    tokens.append(piece)
                    yield event("delta", {"text": piece})
                answer = "".join(tokens)
                result = history.complete_cloud_exchange(
                    database, body.requestId, body.conversationId, text, answer)
                completed = True
                yield event("done", result)
            except asyncio.CancelledError:
                raise
            except cloud.CloudError as exc:
                yield event("error", {"message": str(exc)})
            except Exception:
                yield event("error", {"message": "Поток прервался. Запрос мог быть обработан Cloud.ru; "
                    "повтор с тем же ID заблокирован."})
            finally:
                if reserved and not completed:
                    db.fail_request(database, body.requestId)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-store", "X-Accel-Buffering": "no",
        })

    @app.get("/api/conversations")
    def list_conversations() -> dict:
        return {"conversations": history.list_conversations(database)}

    @app.post("/api/conversations", status_code=201)
    def add_conversation(body: ConversationInput) -> dict:
        if not body.title.strip():
            raise HTTPException(422, detail="Название не может быть пустым.")
        return history.create_conversation(database, body.title.strip())

    @app.put("/api/conversations/{conv_id}")
    def rename_conversation(conv_id: str, body: ConversationInput) -> dict:
        if not body.title.strip():
            raise HTTPException(422, detail="Название не может быть пустым.")
        if not history.rename_conversation(database, conv_id, body.title.strip()):
            raise HTTPException(404, detail="Диалог не найден.")
        return {"success": True}

    @app.delete("/api/conversations/{conv_id}")
    def delete_conversation(conv_id: str) -> dict:
        if conv_id == "main":
            raise HTTPException(409, detail="Основной диалог нельзя удалить; можно очистить его историю.")
        if not history.delete_conversation(database, conv_id):
            raise HTTPException(404, detail="Диалог не найден или в нём ещё выполняется запрос.")
        return {"success": True}

    @app.get("/api/chat/search")
    def search_chat(q: str = Query(min_length=2, max_length=100), conversationId: str | None = None):
        if conversationId is not None:
            require_conversation(conversationId)
        return {"matches": history.search_messages(database, q.strip(), conversationId)}

    @app.get("/api/memory/facts")
    def list_memory_facts():
        return {"facts": history.list_facts(database)}

    @app.post("/api/memory/facts", status_code=201)
    def create_memory_fact(body: FactInput):
        if not body.content.strip():
            raise HTTPException(422, detail="Факт не должен быть пустым.")
        try:
            return history.add_fact(database, body.content.strip())
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from None

    @app.delete("/api/memory/facts/{fact_id}")
    def delete_memory_fact(fact_id: str):
        if not history.delete_fact(database, fact_id):
            raise HTTPException(404, detail="Факт не найден.")
        return {"success": True}

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

    @app.get("/api/cloud/diagnostics")
    async def cloud_diagnostics() -> dict:
        current = db.cloud_config(database)
        if not cloud.get_key():
            return {"reachable": False, "hasKey": False, "enabled": current["enabled"],
                    "selectedModel": current["model"], "modelAvailable": False,
                    "modelsCount": 0, "message": "Нет сохранённого API-ключа."}
        result = await cloud.diagnose_connection(current["model"])
        return {**result, "hasKey": True, "enabled": current["enabled"],
                "message": "Список моделей Cloud.ru доступен. Это не тест генерации и не проверка оплаты."}

    @app.put("/api/cloud/settings")
    def set_cloud_settings(body: CloudSettingsInput) -> dict:
        if body.model and not cloud.valid_model(body.model):
            raise HTTPException(status_code=422, detail="Некорректный идентификатор модели.")
        if body.enabled and (not body.model or not cloud.get_key()):
            raise HTTPException(status_code=409, detail="Для включения Cloud.ru укажите модель и сохраните ключ.")
        return db.update_cloud_config(database, body.model, body.enabled)

    return app


app = create_app()
