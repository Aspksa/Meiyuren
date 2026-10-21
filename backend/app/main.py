"""Локальный FastAPI API: чат SQLite, память и Cloud.ru Foundation Models."""
from pathlib import Path
from contextlib import asynccontextmanager, closing
import os
import sqlite3
import logging
import asyncio
import json
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import cloud, db, history
from .memory_engine import MemoryEngine, SECRET
from .evolution_runtime import EvolutionRuntime
from .idle import IdleRuntime
from .neural_operations import NeuralOperations
from .replies import generate_reply
from .brain_diagnostics import is_diagnostic_request, diagnostic_report


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
    cloudAllowed: bool = False
    brain: str | None = None


class FactUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    cloudAllowed: bool = False
    revision: int = Field(ge=1)
    expiresAt: int | None = None
    brain: str | None = None


class MemoryPolicyInput(BaseModel):
    allow_cloud_notes: bool | None = None
    allow_cloud_facts: bool | None = None
    auto_extract: bool | None = None
    auto_summaries: bool | None = None
    allow_cloud_embeddings: bool | None = None
    auto_growth: bool | None = None
    auto_evolution: bool | None = None


class CloudBrainsInput(BaseModel):
    brains: dict[str, bool]


class MemoryReviewInput(BaseModel):
    approve: bool
    cloudAllowed: bool = False


class MemoryFeedbackInput(BaseModel):
    helpful: bool


class RecallFeedbackInput(BaseModel):
    memoryId: str = Field(min_length=1, max_length=80)
    helpful: bool


class NeuralFeedbackInput(BaseModel):
    leftId: str = Field(min_length=1,max_length=80)
    rightId: str = Field(min_length=1,max_length=80)
    helpful: bool
    conversationId: str = Field(default='main',max_length=40)



class MemoryNeuralIndexInput(BaseModel):
    itemId: str = Field(min_length=1, max_length=40)
    requestId: str = Field(min_length=36, max_length=36)


class MemoryNeuralSearchInput(BaseModel):
    q: str = Field(min_length=2, max_length=200)
    conversationId: str = Field(default="main", max_length=40)
    requestId: str = Field(min_length=36, max_length=36)


class CloudKeyInput(BaseModel):
    key: str = Field(min_length=8, max_length=2048)


class CloudSettingsInput(BaseModel):
    model: str = Field(max_length=160)
    enabled: bool


def create_app(db_path: Path | None = None) -> FastAPI:
    database = db_path if db_path is not None else db.default_database()
    existed = database.is_file()
    if existed:
        # Резервная копия ДО миграций, а не после изменения старой схемы.
        backup = database.with_name(database.name + ".before-memory-core.bak")
        if not backup.exists():
            temporary = backup.with_name(backup.name + ".tmp")
            try:
                with closing(sqlite3.connect(database)) as source:
                    with closing(sqlite3.connect(temporary)) as dest:
                        source.backup(dest)
                os.replace(temporary, backup)
            finally:
                if temporary.exists():
                    temporary.unlink()
    db.initialise(database)
    history.initialise(database)
    engine = MemoryEngine(database)
    engine.initialize(backup_existing=False)
    evolution = EvolutionRuntime(database.with_name('cognitive_evolution.sqlite3'), engine)
    neural_ops = NeuralOperations(database)
    idle = IdleRuntime(database, engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop = asyncio.Event()

        async def worker():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(engine.process_pending, 8)
                    await asyncio.to_thread(evolution.tick)
                    await asyncio.to_thread(neural_ops.tick)
                    await asyncio.to_thread(idle.tick)  # только после 10 минут тишины
                except Exception:
                    logging.getLogger(__name__).exception("Memory worker: локальная задача завершилась с ошибкой")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass

        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            stop.set()
            await task

    app = FastAPI(title="Meiyuren Local API", version="0.28.0", docs_url=None, redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def protect_cloud_settings(request: Request, call_next):
        protected_path = request.url.path.startswith(("/api/cloud/", "/api/chat/", "/api/memory", "/api/conversations", "/api/evolution", "/api/neural", "/api/idle"))
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
        if request.url.path.startswith("/api/chat/") and request.method == "POST":
            idle.touch()  # пользователь пишет: работа простоя ставится на паузу
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

    @app.exception_handler(history.StaleConversation)
    async def stale_chat_handler(_request: Request, error: history.StaleConversation):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.get("/api/neural/operations")
    def neural_operations_status():
        return neural_ops.status()

    @app.post("/api/neural/operations/consolidate")
    def neural_operations_consolidate():
        return neural_ops.tick(force=True)

    @app.get("/api/idle/status")
    def idle_status():
        return idle.status()

    @app.get("/api/idle/briefing")
    def idle_briefing():
        return {"briefing": idle.briefing()}

    @app.post("/api/idle/run")
    async def idle_run():
        return await asyncio.to_thread(idle.tick, force=True)

    @app.post("/api/idle/seen")
    def idle_seen():
        return {"seen": idle.mark_seen()}

    @app.get("/api/evolution/status")
    def evolution_runtime_status():
        return evolution.status()

    @app.post("/api/evolution/evaluate")
    def evolution_runtime_evaluate():
        return evolution.tick(manual=True)

    @app.post("/api/evolution/automatic")
    def evolution_runtime_policy(enabled: bool = Query(...)):
        return evolution.set_enabled(enabled)

    @app.get("/api/health")
    def health() -> dict:
        settings = db.cloud_config(database)
        return {"status": "ok", "engine": "cloud" if settings["enabled"] else "demo", "storage": "sqlite"}

    def require_conversation(conv_id: str) -> None:
        if not history.ensure_conversation(database, conv_id):
            raise HTTPException(status_code=404, detail="Диалог не найден.")

    async def memory_trace(query: str, conversation_id: str, cloud_mode: bool) -> dict:
        # Поиск по памяти синхронный и растёт с её размером: не блокируем event loop.
        return await asyncio.to_thread(engine.prepare_traced, query, conversation_id, cloud_mode)

    def observed(exchange: dict, conv_id: str, trace: dict | None = None) -> dict:
        try:
            engine.observe(exchange, conv_id)
        except Exception:
            # Ошибка индексации не должна превращать уже оплаченный Cloud-ответ в ошибку.
            logging.getLogger(__name__).exception("Memory observe: запись в очередь не удалась")
        if trace and trace.get("traceId"):
            # Какие воспоминания использованы в ответе: их можно оценить прямо в чате.
            exchange = {**exchange, "memory": {"traceId": trace["traceId"], "items": trace["memories"]}}
        return exchange

    def demo_answer(text: str, trace: dict) -> str:
        return generate_reply(text, trace["context"], [m["content"] for m in trace["memories"]])

    @app.get("/api/chat/messages")
    def list_messages(
        limit: int = Query(default=100, ge=1, le=500),
        conversationId: str = Query(default="main", max_length=40),
        before: str | None = Query(default=None, max_length=40),
    ) -> dict:
        require_conversation(conversationId)
        if before:
            return {"messages": history.messages_before(database, conversationId, before, limit)}
        return {"messages": history.messages(database, conversationId, limit)}

    @app.post("/api/chat/messages", status_code=201)
    async def send_message(body: ChatInput) -> dict:
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
        require_conversation(body.conversationId)
        expected_epoch = history.conversation_epoch(database, body.conversationId)
        settings = db.cloud_config(database)
        if is_diagnostic_request(text):
            reply = diagnostic_report(await asyncio.to_thread(engine.status))
            return observed(history.append_exchange(
                database, text, reply, body.conversationId, expected_epoch), body.conversationId)
        trace = await memory_trace(text, body.conversationId, settings["enabled"])
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
                response = await cloud.generate_cloud_reply(settings["model"], previous, trace["context"], text)
                result = history.complete_cloud_exchange(database, body.requestId, body.conversationId, text, response, expected_epoch)
                return observed(result, body.conversationId, trace)
            except Exception:
                # Сохраняем резервирование: повтор с тем же ID не создаст второй платный вызов.
                db.fail_request(database, body.requestId)
                raise
        response = demo_answer(text, trace)
        return observed(history.append_exchange(database, text, response, body.conversationId, expected_epoch),
                        body.conversationId, trace)

    @app.delete("/api/chat/messages")
    def remove_messages(conversationId: str = Query(default="main", max_length=40)) -> dict:
        require_conversation(conversationId)
        deleted = history.clear_messages(database, conversationId)
        engine.purge_conversation(conversationId)
        return {"deleted": deleted}

    @app.post("/api/chat/stream")
    async def stream_message(body: ChatInput):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, detail="Сообщение не может быть пустым.")
        require_conversation(body.conversationId)
        expected_epoch = history.conversation_epoch(database, body.conversationId)
        settings = db.cloud_config(database)
        is_brain_diagnostic = is_diagnostic_request(text)
        if settings["enabled"] and not body.requestId and not is_brain_diagnostic:
            raise HTTPException(422, detail="Для Cloud.ru требуется идентификатор запроса.")
        mode = "cloud" if settings["enabled"] else "demo"

        def event(name, data):
            # Настоящие переводы строк: по пустой строке браузер отделяет SSE-события.
            return "event: " + name + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"

        async def stream():
            reserved = False
            completed = False
            tokens: list[str] = []
            try:
                if is_brain_diagnostic:
                    reply = diagnostic_report(await asyncio.to_thread(engine.status))
                    result = observed(history.append_exchange(
                        database, text, reply, body.conversationId, expected_epoch), body.conversationId)
                    yield event("delta", {"text": reply})
                    yield event("done", result)
                    return
                trace = await memory_trace(text, body.conversationId, settings["enabled"])
                if not settings["enabled"]:
                    result = observed(history.append_exchange(
                        database, text, demo_answer(text, trace),
                        body.conversationId, expected_epoch), body.conversationId, trace)
                    yield event("delta", {"text": result["assistant"]["text"]})
                    yield event("done", result)
                    return
                state, existing = db.reserve_request(database, body.requestId, text)
                if state == "done":
                    yield event("done", existing)
                    return
                if state != "new":
                    yield event("error", {"message": "Запрос уже отправлен или его статус неизвестен. "
                        "Повторная платная отправка заблокирована.", "mode": mode, "paid": True})
                    return
                reserved = True
                history.mark_cloud_conversation(database, body.requestId, body.conversationId)
                previous = history.messages(database, body.conversationId, limit=12)
                async for piece in cloud.stream_cloud_reply(
                    settings["model"], previous, trace["context"], text
                ):
                    tokens.append(piece)
                    yield event("delta", {"text": piece})
                answer = "".join(tokens)
                result = history.complete_cloud_exchange(
                    database, body.requestId, body.conversationId, text, answer, expected_epoch)
                completed = True
                result = observed(result, body.conversationId, trace)
                yield event("done", result)
            except asyncio.CancelledError:
                raise
            except history.StaleConversation:
                yield event("error", {"message": "История диалога очищена во время ответа; ответ не сохранён.",
                                      "mode": mode, "paid": mode == "cloud"})
            except cloud.CloudError as exc:
                saved = interrupted(tokens, str(exc)) if reserved else None
                yield event("error", {"message": str(exc), "mode": mode, "paid": True, "saved": saved})
            except Exception:
                logging.getLogger(__name__).exception("Chat stream: непредвиденная ошибка")
                if mode == "cloud":
                    saved = interrupted(tokens, "Поток прервался") if reserved else None
                    yield event("error", {"message": "Поток прервался. Запрос мог быть обработан Cloud.ru; "
                        "повтор с тем же ID заблокирован.", "mode": mode, "paid": True, "saved": saved})
                else:
                    yield event("error", {"message": "Не удалось обработать сообщение локально. "
                        "Попробуйте ещё раз.", "mode": mode, "paid": False})
            finally:
                if reserved and not completed:
                    db.fail_request(database, body.requestId)
                    if tokens and not saved_once:
                        # Клиент отключился (кнопка «Стоп»): сохраняем уже оплаченную часть.
                        interrupted(tokens, "Ответ остановлен")

        saved_once: list[bool] = []

        def interrupted(tokens: list[str], reason: str) -> dict | None:
            if not tokens or saved_once:
                return None
            saved_once.append(True)
            try:
                return history.save_interrupted_exchange(
                    database, body.requestId, body.conversationId, text, "".join(tokens),
                    reason + " — частичный ответ", expected_epoch)
            except Exception:
                logging.getLogger(__name__).exception("Chat stream: частичный ответ не сохранён")
                return None

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
        engine.purge_conversation(conv_id)
        return {"success": True}

    @app.get("/api/chat/search")
    def search_chat(q: str = Query(min_length=2, max_length=100), conversationId: str | None = None):
        if conversationId is not None:
            require_conversation(conversationId)
        return {"matches": history.search_messages(database, q.strip(), conversationId)}

    @app.get("/api/memory/facts")
    def list_memory_facts():
        return {"facts": engine.items()}

    @app.post("/api/memory/facts", status_code=201)
    def create_memory_fact(body: FactInput):
        try:
            return engine.add_manual(body.content, cloud_allowed=body.cloudAllowed,brain=body.brain)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from None

    @app.put("/api/memory/facts/{fact_id}")
    def update_memory_fact(fact_id: str, body: FactUpdate):
        try:
            item = engine.edit(fact_id, content=body.content, cloud_allowed=body.cloudAllowed,
                               revision=body.revision, expires_at=body.expiresAt,brain=body.brain)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        if item is None:
            raise HTTPException(404, detail="Воспоминание не найдено.")
        return item

    @app.get("/api/memory/facts/{fact_id}/explain")
    def explain_memory_fact(fact_id: str):
        info = engine.explain(fact_id)
        if info is None:
            raise HTTPException(404, detail="Воспоминание не найдено.")
        return info

    @app.delete("/api/memory/facts/{fact_id}")
    def delete_memory_fact(fact_id: str):
        if not engine.forget(fact_id):
            raise HTTPException(404, detail="Воспоминание не найдено.")
        return {"success": True}

    @app.get("/api/memory/candidates")
    def memory_candidates():
        return {"candidates": engine.candidates()}

    @app.post("/api/memory/candidates/{candidate_id}/review")
    def review_memory_candidate(candidate_id: str, body: MemoryReviewInput):
        try:
            result=engine.review(candidate_id,body.approve,body.cloudAllowed)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from None
        if result is None:
            raise HTTPException(404,detail="Предложение не найдено.")
        return result

    @app.get("/api/memory/summaries")
    def memory_summaries():
        return {"summaries": engine.summaries()}

    @app.post("/api/memory/summaries/{conversation_id}/review")
    def review_memory_summary(conversation_id: str, body: MemoryReviewInput):
        try:
            changed=engine.review_summary(conversation_id,body.approve,body.cloudAllowed)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from None
        if not changed:
            raise HTTPException(404,detail="Выписка не найдена.")
        return {"success": True}

    @app.get("/api/memory/episodes")
    def memory_episodes(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.episode_overview(conversationId,cloudMode)

    @app.post("/api/memory/episodes/rebuild")
    def rebuild_memory_episodes():
        return engine.rebuild_episodes()

    @app.get("/api/memory/cortex")
    def cortex_mesh_status(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return {**engine.cortex_status(),
                "provenance":engine.cortex_provenance(conversationId,cloudMode)}

    @app.get("/api/memory/cortex/facts/{fact_id}/connections")
    def cortex_mesh_connections(
        fact_id: str,conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return {"connections":engine.cortex_connections(fact_id,conversationId,cloudMode)}

    @app.post("/api/memory/cortex/rebuild")
    def cortex_mesh_rebuild():
        return engine.rebuild_cortex()

    @app.post("/api/memory/cortex/evaluate")
    def cortex_mesh_evaluate():
        return engine.evaluate_cortex()

    @app.post("/api/memory/neural/feedback")
    def neural_synapse_feedback(body: NeuralFeedbackInput):
        require_conversation(body.conversationId)
        try:
            return engine.neural_feedback(body.leftId,body.rightId,
                                          body.helpful,body.conversationId)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from None

    @app.get("/api/memory/adaptive/overview")
    def adaptive_brain_overview(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.adaptive_brain_overview(conversationId,cloudMode)

    @app.get("/api/memory/omega/overview")
    def omega_overview(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.omega_overview(conversationId,cloudMode)

    @app.get("/api/memory/infinity/overview")
    def infinity_growth_overview(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.infinity_overview(conversationId,cloudMode)

    @app.get("/api/memory/deep/overview")
    def deep_memory_overview(
        conversationId: str = Query(default="main",max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.deep_overview(conversationId,cloudMode)

    @app.get("/api/memory/deep/metrics")
    def deep_memory_metrics():
        return engine.deep_metrics()

    @app.post("/api/memory/deep/rebuild")
    def rebuild_deep_memory():
        return engine.rebuild_deep_index()

    @app.post("/api/memory/deep/facts/{fact_id}/feedback")
    def deep_memory_feedback(fact_id: str,body: MemoryFeedbackInput):
        try:
            return engine.record_feedback(fact_id,body.helpful)
        except ValueError as exc:
            raise HTTPException(404,detail=str(exc)) from None

    @app.get("/api/memory/recall")
    def preview_memory_recall(
        q: str = Query(min_length=2, max_length=200),
        conversationId: str = Query(default="main", max_length=40),
        cloudMode: bool = False,
    ):
        require_conversation(conversationId)
        return engine.preview(q, conversationId, cloudMode)

    @app.post("/api/memory/recall/{trace_id}/feedback")
    def recall_memory_feedback(trace_id: str, body: RecallFeedbackInput):
        try:
            return engine.recall_feedback(trace_id, body.memoryId, body.helpful)
        except LookupError as exc:
            raise HTTPException(404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(404, detail=str(exc)) from None

    @app.get("/api/memory/usage")
    def memory_usage():
        return {"entries": engine.usage()}

    @app.get("/api/memory/tree")
    def autonomous_memory_tree():
        return engine.branch_tree()

    @app.post("/api/memory/tree/rebuild")
    def rebuild_autonomous_memory_tree():
        # Локальная детерминированная пересборка; без Cloud.ru и платных вызовов.
        return engine.grow_branches()

    @app.post("/api/memory/brains/rebuild")
    def rebuild_brain_links():
        return {"links":engine.rebuild_links()}

    @app.get("/api/memory/brains")
    def memory_brains():
        return engine.brains()

    @app.get("/api/memory/brains/{item_id}/links")
    def memory_brain_links(item_id: str):
        if not engine.explain(item_id):
            raise HTTPException(404,detail="Воспоминание не найдено.")
        return {"connections":engine.connections(item_id)}

    @app.post("/api/memory/neural/index")
    async def neural_index(body: MemoryNeuralIndexInput):
        try:
            return await engine.embed_item(body.itemId,body.requestId)
        except ValueError as exc:
            raise HTTPException(409,detail=str(exc)) from None

    @app.post("/api/memory/neural/search")
    async def neural_search(body: MemoryNeuralSearchInput):
        require_conversation(body.conversationId)
        try:
            return {"matches":await engine.neural_search(body.q,body.conversationId,body.requestId)}
        except ValueError as exc:
            raise HTTPException(409,detail=str(exc)) from None

    @app.delete("/api/memory/neural/vectors")
    def clear_neural_vectors():
        return {"deleted":engine.delete_vectors()}

    @app.get("/api/memory/evolution")
    def memory_evolution():
        return engine.evolution_status()

    @app.post("/api/memory/evolution/reset")
    def reset_memory_evolution():
        return engine.reset_evolution()

    @app.post("/api/memory/evolution/evaluate")
    def evaluate_memory_evolution():
        # A single local bounded replay; zero network calls.
        return engine.evolve(force=True)

    @app.get("/api/memory/status")
    def memory_status():
        return engine.status()

    @app.get("/api/memory/policy")
    def memory_policy():
        return engine.policy()

    @app.put("/api/memory/policy")
    def update_memory_policy(body: MemoryPolicyInput):
        updates=body.model_dump(exclude_none=True)
        if updates.get("allow_cloud_notes") and SECRET.search(db.get_memory(database)["notes"]):
            raise HTTPException(422,detail="Заметка содержит потенциальный секрет. Удалите его перед передачей Cloud.ru.")
        try:
            return engine.set_policy(updates)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from None

    @app.get("/api/memory/cloud-brains")
    def memory_cloud_brains():
        return {"brains": engine.cloud_brains(), "enabled": engine.policy()["allow_cloud_facts"]}

    @app.put("/api/memory/cloud-brains")
    def update_memory_cloud_brains(body: CloudBrainsInput):
        try:
            brains=engine.set_cloud_brains(body.brains)
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from None
        return {"brains": brains, "enabled": engine.policy()["allow_cloud_facts"]}

    @app.post("/api/memory/process")
    def run_local_memory_jobs():
        # Только локальная обработка; без сетевого запроса к Cloud.ru.
        return {"processed": engine.process_pending(30), **engine.status()}

    @app.get("/api/memory")
    def read_memory() -> dict:
        return db.get_memory(database)

    @app.put("/api/memory")
    def save_memory(body: MemoryInput) -> dict:
        if engine.policy()["allow_cloud_notes"] and SECRET.search(body.notes):
            raise HTTPException(422,detail="Нельзя передавать заметку с вероятным секретом Cloud.ru.")
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

    @app.get("/api/cloud/compatibility")
    async def cloud_compatibility(model: str = Query(min_length=1, max_length=160)) -> dict:
        # Только GET /models: никакой платной пробной генерации.
        return await cloud.model_compatibility(model)

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
