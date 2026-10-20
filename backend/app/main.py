"""Локальный FastAPI-сервер для истории чата и явных заметок памяти."""
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from . import db
from .replies import generate_reply


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MemoryInput(BaseModel):
    notes: str = Field(max_length=4000)


def create_app(db_path: Path | None = None) -> FastAPI:
    database = db_path if db_path is not None else db.default_database()
    db.initialise(database)
    app = FastAPI(title="Meiyuren Local API", version="0.4.0", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "engine": "demo", "storage": "sqlite"}

    @app.get("/api/chat/messages")
    def list_messages(limit: int = Query(default=100, ge=1, le=500)) -> dict:
        return {"messages": db.messages(database, limit)}

    @app.post("/api/chat/messages", status_code=201)
    def send_message(body: ChatInput) -> dict:
        text = body.text.strip()
        if not text:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Сообщение не может быть пустым")
        notes = db.get_memory(database)["notes"]
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

    return app


app = create_app()
