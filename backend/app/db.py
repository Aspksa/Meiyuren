"""SQLite-хранилище чата и заметок пользователя."""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import time
import uuid


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
