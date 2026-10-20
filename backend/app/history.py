"""Диалоги, полнотекстовый поиск (LIKE) и факты памяти в SQLite.

Старые сообщения автоматически относятся к основному диалогу ('main').
"""
from contextlib import closing
import sqlite3
import time
import uuid

from .db import connection

MAIN = "main"


def initialise(path):
    with closing(connection(path)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.execute("INSERT OR IGNORE INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                         (MAIN, "Основной диалог", int(time.time()*1000), int(time.time()*1000)))
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
            if "conversation_id" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN conversation_id TEXT NOT NULL DEFAULT 'main'")
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(cloud_requests)")}
            if "conversation_id" not in columns:
                conn.execute("ALTER TABLE cloud_requests ADD COLUMN conversation_id TEXT NOT NULL DEFAULT 'main'")
            conv_columns = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
            if "generation" not in conv_columns:
                conn.execute("ALTER TABLE conversations ADD COLUMN generation INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv_time ON messages(conversation_id, sent_at)")


class StaleConversation(RuntimeError):
    """История очищена во время ответа; запрещена запись из старого поколения."""


def conversation_epoch(path, conv_id):
    with closing(connection(path)) as conn:
        row = conn.execute("SELECT generation FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if row is None:
        raise StaleConversation("Диалог удалён во время генерации.")
    return row["generation"]


def ensure_conversation(path, conv_id):
    with closing(connection(path)) as conn:
        row = conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
    return row is not None


def list_conversations(path):
    with closing(connection(path)) as conn:
        rows = conn.execute("SELECT id, title, created_at, updated_at FROM conversations "
                            "ORDER BY updated_at DESC, id ASC LIMIT 100").fetchall()
    return [dict(id=r["id"], title=r["title"], createdAt=r["created_at"], updatedAt=r["updated_at"]) for r in rows]


def create_conversation(path, title):
    now = int(time.time()*1000)
    conv_id = str(uuid.uuid4())
    with closing(connection(path)) as conn:
        with conn:
            conn.execute("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)", (conv_id, title, now, now))
    return {"id": conv_id, "title": title, "createdAt": now, "updatedAt": now}


def rename_conversation(path, conv_id, title):
    with closing(connection(path)) as conn:
        with conn:
            changed = conn.execute("UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                                   (title, int(time.time()*1000), conv_id)).rowcount
    return changed > 0


def delete_conversation(path, conv_id):
    if conv_id == MAIN:
        return False
    with closing(connection(path)) as conn:
        with conn:
            exists = conn.execute("SELECT 1 FROM conversations WHERE id=?", (conv_id,)).fetchone()
            if not exists:
                return False
            ongoing = conn.execute(
                "SELECT COUNT(*) FROM cloud_requests WHERE conversation_id=? AND state='pending'",
                (conv_id,),
            ).fetchone()[0]
            if ongoing:
                return False
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            # Сохраняем идентификаторы Cloud-запросов, предотвращая повторное списание.
            conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    return True


def messages(path, conv_id=MAIN, limit=200):
    with closing(connection(path)) as conn:
        rows = conn.execute(
            "SELECT id,role,text,sent_at FROM (SELECT rowid,id,role,text,sent_at FROM messages "
            "WHERE conversation_id=? ORDER BY rowid DESC LIMIT ?) ORDER BY rowid",
            (conv_id, limit)
        ).fetchall()
    return [dict(id=r["id"],role=r["role"],text=r["text"],sentAt=r["sent_at"]) for r in rows]


def clear_messages(path, conv_id):
    with closing(connection(path)) as conn:
        with conn:
            conn.execute("UPDATE conversations SET generation=generation+1,updated_at=? WHERE id=?",
                         (int(time.time()*1000),conv_id))
            count = conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,)).rowcount
            # Очищение истории не снимает блокировки неопределённых платных запросов.
            # Сохраняем журнал ID даже после очистки истории для защиты от повторной оплаты.
    return count


def append_exchange(path, user_text, answer, conv_id, expected_epoch=None):
    now = int(time.time()*1000)
    user = dict(id=uuid.uuid4().hex,role="user",text=user_text,sentAt=now)
    assistant = dict(id=uuid.uuid4().hex,role="assistant",text=answer,sentAt=now+1)
    with closing(connection(path)) as conn:
        with conn:
            if expected_epoch is not None:
                row=conn.execute("SELECT generation FROM conversations WHERE id=?", (conv_id,)).fetchone()
                if row is None or row["generation"] != expected_epoch:
                    raise StaleConversation("История диалога очищена во время ответа.")
            conn.executemany(
                "INSERT INTO messages(id,role,text,sent_at,conversation_id) VALUES(?,?,?,?,?)",
                [(r["id"],r["role"],r["text"],r["sentAt"],conv_id) for r in (user,assistant)])
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now,conv_id))
    return dict(user=user,assistant=assistant)


def search_messages(path, query, conv_id=None, limit=50):
    # Экранируем шаблонные метасимволы LIKE.
    escaped = query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
    pattern = "%" + escaped + "%"
    sql = ("SELECT id,role,text,sent_at,conversation_id FROM messages WHERE text LIKE ? ESCAPE '\\'")
    params = [pattern]
    if conv_id is not None:
        sql += " AND conversation_id=?"
        params.append(conv_id)
    sql += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    with closing(connection(path)) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(id=r["id"],role=r["role"],text=r["text"],sentAt=r["sent_at"],conversationId=r["conversation_id"]) for r in rows]


def list_facts(path):
    with closing(connection(path)) as conn:
        rows = conn.execute("SELECT id,content,created_at FROM memory_facts ORDER BY created_at DESC, id DESC LIMIT 100").fetchall()
    return [dict(id=r["id"],content=r["content"],createdAt=r["created_at"]) for r in rows]


def add_fact(path, content):
    item = dict(id=str(uuid.uuid4()),content=content,createdAt=int(time.time()*1000))
    with closing(connection(path)) as conn:
        with conn:
            count = conn.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0]
            if count >= 100:
                raise ValueError("Сохранено максимально допустимое количество фактов (100).")
            conn.execute("INSERT INTO memory_facts VALUES(?,?,?)",(item["id"],content,item["createdAt"]))
    return item


def delete_fact(path, fact_id):
    with closing(connection(path)) as conn:
        with conn:
            result=conn.execute("DELETE FROM memory_facts WHERE id=?",(fact_id,)).rowcount
    return result>0


def mark_cloud_conversation(path,request_id,conv_id):
    with closing(connection(path)) as conn:
        with conn:
            conn.execute("UPDATE cloud_requests SET conversation_id=? WHERE request_id=?",(conv_id,request_id))


def complete_cloud_exchange(path, request_id, conv_id, user_text, answer, expected_epoch=None):
    now=int(time.time()*1000)
    user=dict(id=uuid.uuid4().hex,role="user",text=user_text,sentAt=now)
    assistant=dict(id=uuid.uuid4().hex,role="assistant",text=answer,sentAt=now+1)
    with closing(connection(path)) as conn:
        with conn:
            if expected_epoch is not None:
                row=conn.execute("SELECT generation FROM conversations WHERE id=?", (conv_id,)).fetchone()
                if row is None or row["generation"] != expected_epoch:
                    raise StaleConversation("История очищена во время ответа Cloud.ru. "
                                            "Повторная платная отправка не выполняется.")
            conn.executemany(
                "INSERT INTO messages(id,role,text,sent_at,conversation_id) VALUES(?,?,?,?,?)",
                [(r["id"],r["role"],r["text"],r["sentAt"],conv_id) for r in (user,assistant)])
            changed=conn.execute(
                "UPDATE cloud_requests SET state='done',user_message_id=?,assistant_message_id=? "
                "WHERE request_id=? AND state='pending' AND conversation_id=?",
                (user["id"],assistant["id"],request_id,conv_id)).rowcount
            if changed!=1:
                raise RuntimeError("Cloud-запрос не может быть завершён повторно")
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now,conv_id))
    return dict(user=user,assistant=assistant)
