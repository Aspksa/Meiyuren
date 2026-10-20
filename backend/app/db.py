"""SQLite-хранилище чата и заметок пользователя."""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import time
import uuid
import hashlib


def default_database() -> Path:
    override = os.environ.get("MEIYUREN_DATA_DIR")
    directory = Path(override).expanduser() if override else Path(__file__).resolve().parents[2] / "data"
    return directory / "meiyuren.sqlite3"


def connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialise(path: Path) -> None:
    with closing(connection(path)) as db:
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    text TEXT NOT NULL,
                    sent_at INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS cloud_requests (
                    request_id TEXT PRIMARY KEY,
                    text_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('pending', 'done', 'unknown')),
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS cloud_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    model TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1))
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS profile_memory (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
            """)


def messages(path: Path, limit: int = 100) -> list[dict]:
    with closing(connection(path)) as db:
        rows = db.execute(
            "SELECT id, role, text, sent_at FROM "
            "(SELECT id, role, text, sent_at, rowid FROM messages ORDER BY rowid DESC LIMIT ?) "
            "ORDER BY rowid ASC",
            (limit,),
        ).fetchall()
    return [
        {"id": row["id"], "role": row["role"], "text": row["text"], "sentAt": row["sent_at"]}
        for row in rows
    ]


def append_exchange(path: Path, user_text: str, assistant_text: str) -> dict:
    # Оба сообщения записываются атомарно в одной транзакции.
    now = int(time.time() * 1000)
    items = [
        {"id": uuid.uuid4().hex, "role": "user", "text": user_text, "sentAt": now},
        {"id": uuid.uuid4().hex, "role": "assistant", "text": assistant_text, "sentAt": now + 1},
    ]
    with closing(connection(path)) as db:
        with db:
            db.executemany(
                "INSERT INTO messages (id, role, text, sent_at) VALUES (?, ?, ?, ?)",
                [(x["id"], x["role"], x["text"], x["sentAt"]) for x in items],
            )
    return {"user": items[0], "assistant": items[1]}


def clear_messages(path: Path) -> int:
    with closing(connection(path)) as db:
        with db:
            count = db.execute("DELETE FROM messages").rowcount
    return count


def get_memory(path: Path) -> dict:
    with closing(connection(path)) as db:
        row = db.execute("SELECT notes, updated_at FROM profile_memory WHERE id = 1").fetchone()
    return {"notes": row["notes"], "updatedAt": row["updated_at"]} if row else {"notes": "", "updatedAt": None}


def put_memory(path: Path, notes: str) -> dict:
    now = int(time.time() * 1000)
    with closing(connection(path)) as db:
        with db:
            db.execute(
                "INSERT INTO profile_memory (id, notes, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET notes = excluded.notes, updated_at = excluded.updated_at",
                (notes, now),
            )
    return {"notes": notes, "updatedAt": now}

def cloud_config(path: Path) -> dict:
    with closing(connection(path)) as db:
        row = db.execute("SELECT model, enabled FROM cloud_settings WHERE id = 1").fetchone()
    return {"model": row["model"], "enabled": bool(row["enabled"])} if row else {"model": "", "enabled": False}


def update_cloud_config(path: Path, model: str, enabled: bool) -> dict:
    with closing(connection(path)) as db:
        with db:
            db.execute(
                "INSERT INTO cloud_settings(id, model, enabled) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET model=excluded.model, enabled=excluded.enabled",
                (model, int(enabled)),
            )
    return {"model": model, "enabled": enabled}

def reserve_request(path: Path, request_id: str, text: str) -> tuple[str, dict | None]:
    # UUID проверяется здесь: request_id используется только как значение SQL, не в путях.
    try:
        identifier = str(uuid.UUID(request_id))
    except (ValueError, AttributeError):
        return "invalid", None
    if identifier != request_id:
        return "invalid", None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with closing(connection(path)) as db:
        with db:
            created = db.execute(
                "INSERT OR IGNORE INTO cloud_requests(request_id,text_digest,state,created_at) "
                "VALUES(?,?,'pending',?)", (identifier, digest, int(time.time() * 1000))
            ).rowcount
            if created:
                return "new", None
            row = db.execute("SELECT * FROM cloud_requests WHERE request_id=?", (identifier,)).fetchone()
            if row["text_digest"] != digest:
                return "conflict", None
            if row["state"] != "done":
                return row["state"], None
            user = db.execute(
                "SELECT id,role,text,sent_at FROM messages WHERE id=?", (row["user_message_id"],)
            ).fetchone()
            assistant = db.execute(
                "SELECT id,role,text,sent_at FROM messages WHERE id=?", (row["assistant_message_id"],)
            ).fetchone()
            if user and assistant:
                return "done", {
                    "user": dict(id=user["id"], role=user["role"], text=user["text"], sentAt=user["sent_at"]),
                    "assistant": dict(id=assistant["id"], role=assistant["role"], text=assistant["text"], sentAt=assistant["sent_at"]),
                }
    return "unknown", None


def finish_request(path: Path, request_id: str, user_text: str, assistant_text: str) -> dict:
    now = int(time.time() * 1000)
    user = {"id": uuid.uuid4().hex, "role": "user", "text": user_text, "sentAt": now}
    assistant = {"id": uuid.uuid4().hex, "role": "assistant", "text": assistant_text, "sentAt": now + 1}
    with closing(connection(path)) as db:
        with db:
            db.executemany(
                "INSERT INTO messages(id,role,text,sent_at) VALUES(?,?,?,?)",
                [(x["id"], x["role"], x["text"], x["sentAt"]) for x in (user, assistant)],
            )
            changed = db.execute(
                "UPDATE cloud_requests SET state='done',user_message_id=?,assistant_message_id=? "
                "WHERE request_id=? AND state='pending'",
                (user["id"], assistant["id"], request_id),
            ).rowcount
            if changed != 1:
                raise RuntimeError("Cloud-запрос уже был завершён")
    return {"user": user, "assistant": assistant}


def fail_request(path: Path, request_id: str) -> None:
    with closing(connection(path)) as db:
        with db:
            db.execute(
                "UPDATE cloud_requests SET state='unknown' WHERE request_id=? AND state='pending'",
                (request_id,),
            )
