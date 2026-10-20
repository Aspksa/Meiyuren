"""Memory Core: локальная проверяемая память, поиск, очередь и политика приватности.

Никаких фоновых Cloud.ru запросов. Старые заметки остаются в profile_memory,
ручные memory_facts импортируются как legacy без выдуманных источников.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import re
import sqlite3
import time
import uuid

from . import db

MAX_CONTEXT = 1700
TOKENS = re.compile(r"[^\W_]+", re.UNICODE)
SECRET = re.compile(
    r"(?i)(?:api[\s_-]*key|secret|token|парол[ьи]|ключ[\s_-]*api|"
    r"bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|"
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b|"
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,})"
)
RUSSIAN_SUFFIXES = tuple(sorted((
    "иями", "ями", "ами", "иях", "ого", "ему", "ими", "иях",
    "иях", "иях", "иям", "ием", "иях", "ость", "ости", "ыми",
    "иях", "иях", "ыми", "ими", "ает", "яют", "ать", "ить",
    "иях", "ах", "ях", "ов", "ев", "ей", "ой", "ий", "ый",
    "ая", "ое", "ые", "ие", "ии", "ам", "ям", "ом", "ем",
    "у", "ю", "а", "я", "ы", "и", "е", "о",
), key=len, reverse=True))
def preference_topic(content: str) -> tuple[str, bool] | None:
    phrase = content.strip().rstrip(".! ")
    denied = NEGATIVE_PREFERENCE.match(phrase)
    positive = PREFERENCE.match(phrase)
    if not (denied or positive):
        return None
    topic = canonical((denied or positive).group(1))
    return (topic, bool(positive))


STOPWORDS = frozenset(("мне","что","это","как","или","для","мой","моя","мои","когда",
                      "где","наш","ваш","могу","можно","есть","еще","ещё","хочу",
                      "тебе","меня","будет","было","были","кто","про"))


def search_stem(token: str) -> str:
    if not re.search(r"[а-яё]", token):
        return token
    for suffix in RUSSIAN_SUFFIXES:
        if token.endswith(suffix) and len(token)-len(suffix)>=4:
            return token[:-len(suffix)]
    return token


NEGATIVE_PREFERENCE = re.compile(
    r"(?is)^\s*(?:я\s+(?:больше\s+)?не\s+люблю|"
    r"мне\s+(?:больше\s+)?не\s+нрав(?:ится|ятся))\s+(.{3,250})\s*$"
)
EXPLICIT = re.compile(r"(?is)^\s*(?:пожалуйста[, ]+)?запомни[, :]+(?:что\s+)?(.{4,400})\s*$")
PREFERENCE = re.compile(
    r"(?is)^\s*(?:я\s+(?:люблю|предпочитаю)\b|мне\s+нрав(?:ится|ятся)\b)\s+(.{3,350})\s*$"
)


def now() -> int:
    return int(time.time() * 1000)


def canonical(content: str) -> str:
    return " ".join(content.casefold().split())


def digest(content: str) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


class MemoryEngine:
    """Один SQLite-backed сервис; тяжёлые операции выполняются после ответа."""

    def __init__(self, path: Path):
        self.path = path

    def initialize(self, backup_existing: bool = False) -> None:
        # Backup API читает консистентный снимок даже если WAL активен.
        with closing(db.connection(self.path)) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_items'"
            ).fetchone()
        if backup_existing and not exists:
            backup = self.path.with_name(self.path.name + ".before-memory-core.bak")
            if not backup.exists():
                with closing(sqlite3.connect(self.path)) as source:
                    with closing(sqlite3.connect(backup)) as dest:
                        source.backup(dest)
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'fact', status TEXT NOT NULL
                      CHECK(status IN ('confirmed','superseded')),
                    source_message_id TEXT, conversation_id TEXT NOT NULL DEFAULT 'global',
                    cloud_allowed INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    expires_at INTEGER, revision INTEGER NOT NULL DEFAULT 1
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    source_message_id TEXT NOT NULL UNIQUE, conversation_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
                    created_at INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_tombstones (
                    fingerprint TEXT PRIMARY KEY, created_at INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_excluded_sources (
                    source_message_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_revisions (
                    id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, action TEXT NOT NULL,
                    content TEXT NOT NULL, created_at INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_recall_log (
                    id TEXT PRIMARY KEY, memory_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, cloud_mode INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_recall_memory ON memory_recall_log(memory_id)")

                conn.execute("""CREATE TABLE IF NOT EXISTS memory_policy (
                    id INTEGER PRIMARY KEY CHECK(id=1), allow_cloud_notes INTEGER NOT NULL DEFAULT 0,
                    allow_cloud_facts INTEGER NOT NULL DEFAULT 0,
                    auto_extract INTEGER NOT NULL DEFAULT 1,
                    auto_summaries INTEGER NOT NULL DEFAULT 1
                )""")
                conn.execute("INSERT OR IGNORE INTO memory_policy(id) VALUES(1)")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_summaries (
                    conversation_id TEXT PRIMARY KEY, content TEXT NOT NULL,
                    source_message_id TEXT NOT NULL, status TEXT NOT NULL
                      CHECK(status IN ('draft','approved','invalid')),
                    cloud_allowed INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS memory_jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    ref_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending','running','done','failed')),
                    lease_until INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    UNIQUE(kind, ref_id)
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_items_status ON memory_items(status,updated_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_jobs_state ON memory_jobs(state,lease_until)")
                columns={r["name"] for r in conn.execute("PRAGMA table_info(memory_candidates)")}
                if "conflict_with" not in columns:
                    conn.execute("ALTER TABLE memory_candidates ADD COLUMN conflict_with TEXT")
                item_columns={r["name"] for r in conn.execute("PRAGMA table_info(memory_items)")}
                if "superseded_by" not in item_columns:
                    conn.execute("ALTER TABLE memory_items ADD COLUMN superseded_by TEXT")

                # FTS5 — только локальный индекс. Данные удаляются вместе с фактом.
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(item_id UNINDEXED, content, tokenize='unicode61')")
                legacy = conn.execute("SELECT id,content,created_at FROM memory_facts").fetchall()
                for row in legacy:
                    if not row["content"].strip() or conn.execute(
                        "SELECT 1 FROM memory_tombstones WHERE fingerprint=?", (digest(row["content"]),)
                    ).fetchone():
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO memory_items "
                        "(id,content,fingerprint,kind,status,created_at,updated_at) "
                        "VALUES(?,?,?,'legacy','confirmed',?,?)",
                        (row["id"],row["content"],digest(row["content"]),row["created_at"],row["created_at"]),
                    )
                conn.execute(
                    "INSERT INTO memory_fts(item_id,content) "
                    "SELECT m.id,m.content FROM memory_items m "
                    "WHERE m.status='confirmed' AND NOT EXISTS "
                    "(SELECT 1 FROM memory_fts f WHERE f.item_id=m.id)"
                )

    def policy(self) -> dict:
        with closing(db.connection(self.path)) as conn:
            row=conn.execute("SELECT * FROM memory_policy WHERE id=1").fetchone()
        return {k:bool(row[k]) for k in ("allow_cloud_notes","allow_cloud_facts","auto_extract","auto_summaries")}

    def set_policy(self, updates: dict) -> dict:
        allowed={"allow_cloud_notes","allow_cloud_facts","auto_extract","auto_summaries"}
        if not updates or any(k not in allowed or not isinstance(v,bool) for k,v in updates.items()):
            raise ValueError("Некорректная политика памяти.")
        with closing(db.connection(self.path)) as conn:
            with conn:
                for key,value in updates.items():  # имена проверены allowlist выше
                    conn.execute(f"UPDATE memory_policy SET {key}=? WHERE id=1",(int(value),))
        return self.policy()

    def items(self) -> list[dict]:
        with closing(db.connection(self.path)) as conn:
            rows=conn.execute("SELECT * FROM memory_items WHERE status='confirmed' ORDER BY updated_at DESC LIMIT 300").fetchall()
        return [self._item(r) for r in rows]

    @staticmethod
    def _item(row) -> dict:
        return dict(id=row["id"],content=row["content"],createdAt=row["created_at"],
                    updatedAt=row["updated_at"],kind=row["kind"],sourceMessageId=row["source_message_id"],
                    conversationId=row["conversation_id"],cloudAllowed=bool(row["cloud_allowed"]),
                    expiresAt=row["expires_at"],revision=row["revision"],status=row["status"],
                    supersededBy=row["superseded_by"])

    def add_manual(self, content: str, *, cloud_allowed: bool=False) -> dict:
        content=content.strip()
        if not 1<=len(content)<=500:
            raise ValueError("Факт должен содержать от 1 до 500 символов.")
        if SECRET.search(content):
            raise ValueError("Похоже на секрет или персональный идентификатор. Не сохраняйте его в память.")
        ts=now()
        item_id=str(uuid.uuid4())
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM memory_tombstones WHERE fingerprint=?", (digest(content),))
                conn.execute(
                    "INSERT INTO memory_revisions VALUES(?,?,?,?,?,?)",
                    (str(uuid.uuid4()),item_id,1,"created",content,ts))
                conn.execute(
                    "INSERT INTO memory_items(id,content,fingerprint,kind,status,cloud_allowed,created_at,updated_at) "
                    "VALUES(?,?,?,'manual','confirmed',?,?,?)",
                    (item_id,content,digest(content),int(cloud_allowed),ts,ts))
                conn.execute("INSERT INTO memory_fts(item_id,content) VALUES(?,?)",(item_id,content))
                row=conn.execute("SELECT * FROM memory_items WHERE id=?",(item_id,)).fetchone()
        return self._item(row)

    def edit(self, item_id: str, *, content: str, cloud_allowed: bool, revision: int,
             expires_at: int | None = None) -> dict | None:
        content=content.strip()
        if not 1<=len(content)<=500 or SECRET.search(content):
            raise ValueError("Недопустимое содержание воспоминания.")
        with closing(db.connection(self.path)) as conn:
            with conn:
                old=conn.execute("SELECT * FROM memory_items WHERE id=? AND status='confirmed'",(item_id,)).fetchone()
                if not old:
                    return None
                if old["revision"]!=revision:
                    raise ValueError("Воспоминание изменилось в другом окне. Перезагрузите список.")
                if digest(old["content"]) != digest(content):
                    conn.execute("INSERT OR IGNORE INTO memory_tombstones VALUES(?,?)",
                                 (old["fingerprint"],now()))
                conn.execute("INSERT INTO memory_revisions VALUES(?,?,?,?,?,?)",
                             (str(uuid.uuid4()),item_id,revision+1,"edited",content,now()))
                conn.execute("DELETE FROM memory_fts WHERE item_id=?",(item_id,))
                conn.execute(
                    "UPDATE memory_items SET content=?,fingerprint=?,cloud_allowed=?,expires_at=?,"
                    "updated_at=?,revision=revision+1 WHERE id=?",
                    (content,digest(content),int(cloud_allowed),expires_at,now(),item_id))
                conn.execute("INSERT INTO memory_fts(item_id,content) VALUES(?,?)",(item_id,content))
                row=conn.execute("SELECT * FROM memory_items WHERE id=?",(item_id,)).fetchone()
        return self._item(row)

    def forget(self, item_id: str) -> bool:
        with closing(db.connection(self.path)) as conn:
            with conn:
                old=conn.execute("SELECT * FROM memory_items WHERE id=?",(item_id,)).fetchone()
                if not old:
                    return False
                conn.execute("INSERT OR IGNORE INTO memory_tombstones VALUES(?,?)",(old["fingerprint"],now()))
                conn.execute("DELETE FROM memory_fts WHERE item_id=?",(item_id,))
                conn.execute("DELETE FROM memory_items WHERE id=?",(item_id,))
                # В предыдущих версиях копия ручного факта оставалась в memory_facts.
                conn.execute("DELETE FROM memory_facts WHERE id=?",(item_id,))
                conn.execute("DELETE FROM memory_revisions WHERE memory_id=?",(item_id,))
                conn.execute("DELETE FROM memory_recall_log WHERE memory_id=?",(item_id,))
                if old["source_message_id"]:
                    conn.execute("INSERT OR IGNORE INTO memory_excluded_sources VALUES(?,?)",
                                 (old["source_message_id"],now()))
                conn.execute("DELETE FROM memory_candidates WHERE fingerprint=?",(old["fingerprint"],))
                # Не оставляем производные сводки с потенциально удалённой информацией.
                if old["conversation_id"]!="global":
                    conn.execute("DELETE FROM memory_summaries WHERE conversation_id=?",
                                 (old["conversation_id"],))
                else:
                    conn.execute("DELETE FROM memory_summaries")
        return True

    def explain(self,item_id: str) -> dict | None:
        with closing(db.connection(self.path)) as conn:
            row=conn.execute("SELECT * FROM memory_items WHERE id=?",(item_id,)).fetchone()
            if not row:
                return None
            source=None
            if row["source_message_id"]:
                src=conn.execute("SELECT id,text FROM messages WHERE id=? AND role='user'",
                                 (row["source_message_id"],)).fetchone()
                if src:
                    source=dict(id=src["id"],text=src["text"])
        return dict(item=self._item(row),source=source,sourceAvailable=source is not None)

    def candidates(self) -> list[dict]:
        with closing(db.connection(self.path)) as conn:
            rows=conn.execute("SELECT * FROM memory_candidates WHERE status='pending' "
                              "ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(id=r["id"],content=r["content"],sourceMessageId=r["source_message_id"],
                     conversationId=r["conversation_id"],createdAt=r["created_at"],
                     conflictWith=r["conflict_with"]) for r in rows]

    def review(self,candidate_id: str,approve: bool,cloud_allowed: bool=False) -> dict | None:
        with closing(db.connection(self.path)) as conn:
            with conn:
                row=conn.execute("SELECT * FROM memory_candidates WHERE id=? AND status='pending'",
                                 (candidate_id,)).fetchone()
                if not row:
                    return None
                if not approve:
                    conn.execute("UPDATE memory_candidates SET status='rejected' WHERE id=?",(candidate_id,))
                    conn.execute("INSERT OR IGNORE INTO memory_tombstones VALUES(?,?)",
                                 (row["fingerprint"],now()))
                    return dict(approved=False)
                if SECRET.search(row["content"]):
                    raise ValueError("Нельзя сохранять обнаруженный секрет.")
                item_id=str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO memory_items(id,content,fingerprint,kind,status,source_message_id,"
                    "conversation_id,cloud_allowed,created_at,updated_at) "
                    "VALUES(?,?,?,'extracted','confirmed',?,?,?,?,?)",
                    (item_id,row["content"],row["fingerprint"],row["source_message_id"],
                     row["conversation_id"],int(cloud_allowed),now(),now()))
                conn.execute("INSERT INTO memory_fts(item_id,content) VALUES(?,?)",(item_id,row["content"]))
                conn.execute("INSERT INTO memory_revisions VALUES(?,?,?,?,?,?)",
                             (str(uuid.uuid4()),item_id,1,"approved",row["content"],now()))
                if row["conflict_with"]:
                    previous=conn.execute("SELECT id,content FROM memory_items WHERE id=? AND status='confirmed'",
                                          (row["conflict_with"],)).fetchone()
                    if previous:
                        old_topic=preference_topic(previous["content"])
                        new_topic=preference_topic(row["content"])
                        if old_topic and new_topic and old_topic[0]==new_topic[0] and old_topic[1]!=new_topic[1]:
                            conn.execute(
                                "UPDATE memory_items SET status='superseded',cloud_allowed=0,"
                                "superseded_by=?,updated_at=? WHERE id=?",
                                (item_id,now(),previous["id"]))
                            conn.execute("DELETE FROM memory_fts WHERE item_id=?",(previous["id"],))
                            conn.execute("DELETE FROM memory_summaries")
                conn.execute("UPDATE memory_candidates SET status='approved' WHERE id=?",(candidate_id,))
                item=conn.execute("SELECT * FROM memory_items WHERE id=?",(item_id,)).fetchone()
        return dict(approved=True,item=self._item(item))

    def observe(self,exchange: dict,conversation_id: str) -> None:
        """Быстрая постановка идемпотентных локальных задач после сохранения ответа."""
        user=exchange["user"]
        ts=now()
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO memory_jobs(id,kind,ref_id,conversation_id,state,created_at) "
                    "VALUES(?,'extract',?,?,'pending',?)",
                    (str(uuid.uuid4()),user["id"],conversation_id,ts))
                # Сводку обновляем только после каждых шести пар сообщений.
                total=conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id=?",(conversation_id,)
                ).fetchone()[0]
                if total>=12 and total % 12 == 0:
                    conn.execute(
                        "INSERT OR IGNORE INTO memory_jobs(id,kind,ref_id,conversation_id,state,created_at) "
                        "VALUES(?,'summary',?,?,'pending',?)",
                        (str(uuid.uuid4()),user["id"],conversation_id,ts))

    def process_pending(self,limit: int=10) -> int:
        """Единственный локальный worker; lease позволяет восстановиться после перезапуска."""
        done=0
        for _ in range(min(limit,50)):
            with closing(db.connection(self.path)) as conn:
                with conn:
                    # Завершённые задания не должны копиться бесконечно.
                    conn.execute("DELETE FROM memory_jobs WHERE state IN ('done','failed') AND created_at<?",
                                 (now()-7*24*3600*1000,))
                    conn.execute("UPDATE memory_jobs SET state='failed',lease_until=0 "
                                 "WHERE state='running' AND lease_until<? AND attempts>=3",(now(),))
                    row=conn.execute(
                        "SELECT * FROM memory_jobs WHERE state='pending' OR "
                        "(state='running' AND lease_until<? AND attempts<3) ORDER BY created_at,id LIMIT 1",
                        (now(),)).fetchone()
                    if not row:
                        break
                    leased=conn.execute(
                        "UPDATE memory_jobs SET state='running',lease_until=?,attempts=attempts+1 "
                        "WHERE id=? AND (state='pending' OR (state='running' AND lease_until<?))",
                        (now()+30000,row["id"],now())
                    ).rowcount
                    if leased!=1:
                        continue
            try:
                if row["kind"]=="extract" and self.policy()["auto_extract"]:
                    self._extract(row["ref_id"],row["conversation_id"])
                if row["kind"]=="summary" and self.policy()["auto_summaries"]:
                    self._summarize(row["conversation_id"],row["ref_id"])
                with closing(db.connection(self.path)) as conn:
                    with conn:
                        conn.execute("UPDATE memory_jobs SET state='done',lease_until=0 WHERE id=?",
                                     (row["id"],))
                done+=1
            except (sqlite3.Error, ValueError):
                with closing(db.connection(self.path)) as conn:
                    with conn:
                        conn.execute("UPDATE memory_jobs SET state='failed',lease_until=0 WHERE id=?",
                                     (row["id"],))
        return done

    def _extract(self,message_id: str,conversation_id: str) -> None:
        with closing(db.connection(self.path)) as conn:
            msg=conn.execute("SELECT text FROM messages WHERE id=? AND role='user' AND conversation_id=?",
                             (message_id,conversation_id)).fetchone()
            if not msg:
                return
            text=msg["text"].strip()
            if SECRET.search(text):
                return
            explicit=EXPLICIT.match(text)
            implicit=PREFERENCE.match(text) or NEGATIVE_PREFERENCE.match(text)
            candidate=(explicit or implicit)
            if not candidate:
                return
            content=(candidate.group(1) if explicit else text).strip().rstrip(".")
            if not 4<=len(content)<=400 or SECRET.search(content):
                return
            fingerprint=digest(content)
            if conn.execute("SELECT 1 FROM memory_tombstones WHERE fingerprint=?",(fingerprint,)).fetchone():
                return
            if conn.execute("SELECT 1 FROM memory_items WHERE fingerprint=? AND status='confirmed'",
                            (fingerprint,)).fetchone():
                return
            if conn.execute("SELECT 1 FROM memory_candidates WHERE fingerprint=? AND status='pending'",
                            (fingerprint,)).fetchone():
                return
            # Конфликт признаём только при явном совпадении темы и противоположной полярности.
            new_topic=preference_topic(content)
            conflict_with=None
            if new_topic:
                existing=conn.execute(
                    "SELECT id,content FROM memory_items WHERE status='confirmed' "
                    "AND (conversation_id='global' OR conversation_id=?)",(conversation_id,)
                ).fetchall()
                for item in existing:
                    old_topic=preference_topic(item["content"])
                    if old_topic and old_topic[0]==new_topic[0] and old_topic[1]!=new_topic[1]:
                        conflict_with=item["id"]
                        break
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO memory_candidates "
                    "(id,content,fingerprint,source_message_id,conversation_id,status,created_at,conflict_with) "
                    "VALUES(?,?,?,?,?,'pending',?,?)",
                    (str(uuid.uuid4()),content,fingerprint,message_id,conversation_id,now(),conflict_with))

    def _summarize(self,conversation_id: str,source_id: str) -> None:
        """Только безопасная выписка подтверждённых фактов с существующими источниками.

        Не цитируем прежние сообщения напрямую: это предотвращает повторное появление
        забытых фактов в сводках после последующей фоновой обработки.
        """
        with closing(db.connection(self.path)) as conn:
            # Длинный диалог — повод пересобрать выписку, но не повод выдумать факты.
            total=conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?",
                               (conversation_id,)).fetchone()[0]
            if total<12:
                return
            selected=conn.execute(
                "SELECT m.content,m.source_message_id FROM memory_items m "
                "JOIN messages source ON source.id=m.source_message_id AND source.role='user' "
                "LEFT JOIN memory_excluded_sources banned ON banned.source_message_id=m.source_message_id "
                "WHERE m.conversation_id=? AND m.status='confirmed' AND banned.source_message_id IS NULL "
                "AND (m.expires_at IS NULL OR m.expires_at>?) "
                "ORDER BY m.updated_at DESC LIMIT 10",(conversation_id,now())
            ).fetchall()
            if not selected:
                # Старые черновики могли содержать отозванные источники.
                with conn:
                    conn.execute("DELETE FROM memory_summaries WHERE conversation_id=?",(conversation_id,))
                return
            old=conn.execute("SELECT * FROM memory_summaries WHERE conversation_id=?",
                             (conversation_id,)).fetchone()
            if old and old["source_message_id"]==source_id:
                return
            content="Выписка из подтверждённых фактов (без исходной переписки):\n"+ "\n".join(
                "• "+r["content"][:200] for r in selected if not SECRET.search(r["content"])
            )
            with conn:
                conn.execute(
                    "INSERT INTO memory_summaries(conversation_id,content,source_message_id,status,updated_at) "
                    "VALUES(?,?,?,'draft',?) ON CONFLICT(conversation_id) DO UPDATE SET "
                    "content=excluded.content,source_message_id=excluded.source_message_id,"
                    "status='draft',cloud_allowed=0,updated_at=excluded.updated_at",
                    (conversation_id,content,source_id,now()))

    def summaries(self) -> list[dict]:
        with closing(db.connection(self.path)) as conn:
            rows=conn.execute("SELECT * FROM memory_summaries WHERE status!='invalid' ORDER BY updated_at DESC").fetchall()
        return [dict(conversationId=r["conversation_id"],content=r["content"],status=r["status"],
                     cloudAllowed=bool(r["cloud_allowed"]),updatedAt=r["updated_at"]) for r in rows]

    def review_summary(self,conversation_id: str,approve: bool,cloud_allowed: bool=False) -> bool:
        with closing(db.connection(self.path)) as conn:
            with conn:
                if approve and cloud_allowed:
                    summary=conn.execute("SELECT content FROM memory_summaries WHERE conversation_id=?",
                                         (conversation_id,)).fetchone()
                    if summary and SECRET.search(summary["content"]):
                        raise ValueError("В выписке обнаружены данные, похожие на секреты.")
                changed=conn.execute(
                    "UPDATE memory_summaries SET status=?,cloud_allowed=?,updated_at=? "
                    "WHERE conversation_id=? AND status IN ('draft','approved')",
                    ("approved" if approve else "invalid",int(approve and cloud_allowed),now(),conversation_id)
                ).rowcount
        return bool(changed)

    def purge_conversation(self,conversation_id: str) -> None:
        with closing(db.connection(self.path)) as conn:
            with conn:
                ids=conn.execute("SELECT id,fingerprint FROM memory_items WHERE conversation_id=?",
                                 (conversation_id,)).fetchall()
                for item in ids:
                    conn.execute("INSERT OR IGNORE INTO memory_tombstones VALUES(?,?)",
                                 (item["fingerprint"],now()))
                    conn.execute("DELETE FROM memory_fts WHERE item_id=?",(item["id"],))
                conn.execute("DELETE FROM memory_revisions WHERE memory_id IN "
                             "(SELECT id FROM memory_items WHERE conversation_id=?)",(conversation_id,))
                conn.execute("DELETE FROM memory_recall_log WHERE memory_id IN "
                             "(SELECT id FROM memory_items WHERE conversation_id=?)",(conversation_id,))
                conn.execute("DELETE FROM memory_items WHERE conversation_id=?",(conversation_id,))
                conn.execute("DELETE FROM memory_candidates WHERE conversation_id=?",(conversation_id,))
                conn.execute("DELETE FROM memory_summaries WHERE conversation_id=?",(conversation_id,))
                conn.execute("DELETE FROM memory_jobs WHERE conversation_id=?",(conversation_id,))

    def prepare(self, query: str,conversation_id: str,cloud_mode: bool) -> str:
        """Read-only recall: у Cloud режима свои разрешения и лимит контекста."""
        policy=self.policy()
        notes=db.get_memory(self.path)["notes"]
        if cloud_mode and not policy["allow_cloud_notes"]:
            notes=""
        parts=[]
        if notes:
            parts.append("Заметка пользователя:\n"+notes[:600])
        words=[w[:20] for w in TOKENS.findall(query.casefold()) if len(w)>=3][:12]
        # Не подмешиваем всю память в нерелевантный ответ.
        if words:
            expr=" OR ".join('"'+w[:max(3,len(w)-2)]+'"*' for w in words)
            with closing(db.connection(self.path)) as conn:
                matches=conn.execute(
                    "SELECT m.* FROM memory_fts f JOIN memory_items m ON m.id=f.item_id "
                    "WHERE memory_fts MATCH ? AND m.status='confirmed' "
                    "AND (m.conversation_id='global' OR m.conversation_id=?) "
                    "AND (m.expires_at IS NULL OR m.expires_at>?) "
                    "ORDER BY bm25(memory_fts) LIMIT 20",
                    (expr,conversation_id,now())).fetchall()
            for row in matches:
                if cloud_mode and not (policy["allow_cloud_facts"] and row["cloud_allowed"]):
                    continue
                parts.append("Подтверждённый факт: "+row["content"])
                if len(parts)>=6:
                    break
        # Сводки включаются только после подтверждения и облачного разрешения.
        with closing(db.connection(self.path)) as conn:
            summary=conn.execute(
                "SELECT content,cloud_allowed FROM memory_summaries WHERE conversation_id=? AND status='approved'",
                (conversation_id,)).fetchone()
        if summary and (not cloud_mode or (policy["allow_cloud_facts"] and summary["cloud_allowed"])):
            if any(w in query.casefold() for w in ("раньше","обсуждал","вспомни","разговор","прошл")):
                parts.append("Проверенная выписка диалога:\n"+summary["content"][:400])
        return "\n".join(parts)[:MAX_CONTEXT]

    def status(self) -> dict:
        with closing(db.connection(self.path)) as conn:
            confirmed=conn.execute("SELECT COUNT(*) FROM memory_items WHERE status='confirmed'").fetchone()[0]
            candidates=conn.execute("SELECT COUNT(*) FROM memory_candidates WHERE status='pending'").fetchone()[0]
            queued=conn.execute("SELECT COUNT(*) FROM memory_jobs WHERE state IN ('pending','running')").fetchone()[0]
            summaries=conn.execute("SELECT COUNT(*) FROM memory_summaries WHERE status='draft'").fetchone()[0]
        return dict(facts=confirmed,pending=candidates,jobs=queued,summaries=summaries,policy=self.policy())
