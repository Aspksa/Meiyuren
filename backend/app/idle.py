"""Idle mode: what Meiyuren does while the user is away.

Runs only after IDLE_AFTER of silence, at most once per RUN_EVERY, entirely
locally (no Cloud.ru, no paid calls). Every step is short and the run stops
between steps as soon as the user writes again, so chat is never slowed.

Steps: consolidation, fact strength, search self-training, briefing for the
next visit, local vectors, integrity check and a daily backup.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import db
from .memory_engine import (
    AUTO_PRIVATE, SECRET, TOKENS, MemoryEngine, _keywords, canonical, now, preference_topic,
    drop_backups, local_vector,
)

IDLE_AFTER = 10 * 60 * 1000
RUN_EVERY = 30 * 60 * 1000
BACKUPS_KEPT = 3
# Strength: recent use and explicit 👍 strengthen, time without use fades.
HALF_LIFE_DAYS = 45
WEAK = 0.12


class IdleRuntime:
    def __init__(self, path: Path, engine: MemoryEngine):
        self.path = path
        self.engine = engine
        self._lock = threading.Lock()
        self._last_activity = now()

    # -- activity ----------------------------------------------------------
    def touch(self) -> None:
        """Called on every chat request: any activity pauses idle work."""
        self._last_activity = now()

    def last_activity(self) -> int:
        with closing(db.connection(self.path)) as conn:
            row = conn.execute("SELECT MAX(sent_at) FROM messages").fetchone()
        return max(self._last_activity, row[0] or 0)

    def _interrupted(self, started: int) -> bool:
        return self._last_activity > started

    # -- scheduling --------------------------------------------------------
    def status(self) -> dict:
        with closing(db.connection(self.path)) as conn:
            last = conn.execute(
                "SELECT * FROM idle_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        idle_for = now() - self.last_activity()
        return {
            "idleAfterMs": IDLE_AFTER, "runEveryMs": RUN_EVERY,
            "idleForMs": max(0, idle_for), "isIdle": idle_for >= IDLE_AFTER,
            "lastRun": self._run(last) if last else None,
            "externalCalls": False,
        }

    @staticmethod
    def _run(row) -> dict:
        return {"id": row["id"], "startedAt": row["started_at"], "finishedAt": row["finished_at"],
                "interrupted": bool(row["interrupted"]), "seen": bool(row["seen"]),
                "report": json.loads(row["report_json"])}

    def briefing(self) -> dict | None:
        """The latest unseen report, for the "while you were away" card."""
        with closing(db.connection(self.path)) as conn:
            row = conn.execute(
                "SELECT * FROM idle_runs WHERE seen=0 AND finished_at IS NOT NULL "
                "ORDER BY started_at DESC LIMIT 1").fetchone()
        return self._run(row) if row else None

    def mark_seen(self) -> int:
        with closing(db.connection(self.path)) as conn:
            with conn:
                return conn.execute("UPDATE idle_runs SET seen=1 WHERE seen=0").rowcount

    def tick(self, *, force: bool = False) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"ran": False, "reason": "busy"}
        try:
            stamp = now()
            if not force:
                if stamp - self.last_activity() < IDLE_AFTER:
                    return {"ran": False, "reason": "active"}
                with closing(db.connection(self.path)) as conn:
                    last = conn.execute("SELECT MAX(started_at) FROM idle_runs").fetchone()[0]
                if last and stamp - last < RUN_EVERY:
                    return {"ran": False, "reason": "interval"}
            return {"ran": True, **self._run_steps(stamp, force)}
        finally:
            self._lock.release()

    def _run_steps(self, started: int, force: bool) -> dict:
        run_id = str(uuid.uuid4())
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("INSERT INTO idle_runs(id,started_at,report_json) VALUES(?,?,'{}')",
                             (run_id, started))
        steps = (
            ("consolidation", self.consolidate),
            ("strength", self.update_strength),
            ("selfTraining", self.self_train),
            ("unfinished", self.unfinished),
            ("vectors", self.vectorize),
            ("health", self.health),
        )
        report: dict = {}
        interrupted = False
        for name, step in steps:
            if not force and self._interrupted(started):
                interrupted = True
                break
            try:
                report[name] = step()
            except (sqlite3.Error, OSError, ValueError) as exc:
                report[name] = {"error": type(exc).__name__}
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE idle_runs SET finished_at=?,interrupted=?,report_json=? WHERE id=?",
                    (now(), int(interrupted), json.dumps(report, ensure_ascii=False), run_id))
                conn.execute("DELETE FROM idle_runs WHERE id NOT IN "
                             "(SELECT id FROM idle_runs ORDER BY started_at DESC LIMIT 50)")
        return {"id": run_id, "interrupted": interrupted, "report": report}

    # -- 1. consolidation --------------------------------------------------
    def consolidate(self) -> dict:
        """Merge automatic near-duplicates, list contradictions for the user.

        Only automatically learned facts are merged, and the newer wording
        wins; the older one becomes superseded, so history stays explainable.
        Manual facts are never touched.
        """
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT id,content,brain,kind,updated_at FROM memory_items WHERE status='confirmed' "
                "AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC LIMIT 1500",
                (now(),)).fetchall()
        auto = [r for r in rows if r["kind"] in ("auto", "extracted")]
        terms = {r["id"]: _keywords(r["content"]) for r in auto}
        merged: list[tuple[str, str]] = []
        gone: set[str] = set()
        for i, newer in enumerate(auto):
            if newer["id"] in gone or not terms[newer["id"]]:
                continue
            for older in auto[i + 1:]:
                if older["id"] in gone or older["brain"] != newer["brain"]:
                    continue
                a, b = terms[newer["id"]], terms[older["id"]]
                if not b:
                    continue
                same = canonical(newer["content"]) == canonical(older["content"])
                overlap = len(a & b) / len(a | b)
                if same or (overlap >= 0.85 and min(len(a), len(b)) >= 2):
                    merged.append((older["id"], newer["id"]))
                    gone.add(older["id"])
        if merged:
            with closing(db.connection(self.path)) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    for old, new in merged:
                        alive = conn.execute(
                            "SELECT 1 FROM memory_items WHERE id IN (?,?) AND status='confirmed'",
                            (old, new)).fetchall()
                        if len(alive) != 2:
                            continue
                        conn.execute("UPDATE memory_items SET status='superseded',cloud_allowed=0,"
                                     "superseded_by=?,updated_at=? WHERE id=?", (new, now(), old))
                        conn.execute("INSERT INTO memory_revisions VALUES(?,?,?,?,?,?)",
                                     (str(uuid.uuid4()), old, 10_000, "merged_while_idle",
                                      "→ " + new, now()))
                        for table in ("memory_fts", "memory_vectors", "memory_local_vectors"):
                            conn.execute(f"DELETE FROM {table} WHERE item_id=?", (old,))
                        conn.execute("DELETE FROM memory_links WHERE left_id=? OR right_id=?", (old, old))
            self.engine.grow_branches()
            self.engine.rebuild_deep_index()
        topics: dict[str, dict[bool, str]] = {}
        for row in rows:
            value = preference_topic(row["content"])
            if value:
                topics.setdefault(value[0], {})[value[1]] = row["content"]
        conflicts = [[v[True], v[False]] for v in topics.values() if len(v) == 2][:10]
        return {"merged": len(merged), "conflicts": conflicts}

    # -- 2. strength -------------------------------------------------------
    def update_strength(self) -> dict:
        """Forgetting curve: use and 👍 strengthen, silence slowly fades."""
        stamp = now()
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT m.id,m.created_at,COALESCE(f.helpful,0) AS helpful,"
                "COALESCE(f.unhelpful,0) AS unhelpful,"
                "(SELECT COUNT(*) FROM memory_recall_log l WHERE l.memory_id=m.id) AS uses,"
                "(SELECT MAX(created_at) FROM memory_recall_log l WHERE l.memory_id=m.id) AS last_use "
                "FROM memory_items m LEFT JOIN memory_deep_feedback f ON f.memory_id=m.id "
                "WHERE m.status='confirmed'").fetchall()
            values = []
            for r in rows:
                last = max(r["last_use"] or 0, r["created_at"])
                days = max(0.0, (stamp - last) / 86_400_000)
                base = 0.45 + 0.05 * min(r["uses"], 8) + 0.15 * r["helpful"] - 0.2 * r["unhelpful"]
                strength = max(0.0, min(1.0, base * 0.5 ** (days / HALF_LIFE_DAYS)))
                values.append((r["id"], round(strength, 4), r["uses"], last, stamp))
            with conn:
                conn.execute("DELETE FROM memory_strength")
                conn.executemany("INSERT INTO memory_strength VALUES(?,?,?,?,?)", values)
        strengths = [v[1] for v in values]
        return {"facts": len(values),
                "strong": sum(s >= 0.6 for s in strengths),
                "fading": sum(s < WEAK for s in strengths)}

    # -- 3. self-training --------------------------------------------------
    def self_train(self) -> dict:
        status = self.engine.evolve(force=True)
        return {"strategy": status["strategy"], "benchmark": status.get("benchmark"),
                "cases": status.get("feedbackCases", 0)}

    # -- 4. briefing for the next visit -------------------------------------
    def unfinished(self) -> dict:
        """Unfinished projects, goals and promises to mention on return."""
        overview = self.engine.deep_overview("main", False)
        items = [item["content"] for item in overview["continuation"]
                 if item["brain"] in ("projects", "goals")
                 and not AUTO_PRIVATE.search(item["content"])][:6]
        return {"items": items}

    # -- 5. local vectors --------------------------------------------------
    def vectorize(self) -> dict:
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT m.id,m.content,m.fingerprint FROM memory_items m "
                "LEFT JOIN memory_local_vectors v ON v.item_id=m.id "
                "WHERE m.status='confirmed' AND (v.item_id IS NULL OR v.digest!=m.fingerprint) "
                "LIMIT 2000").fetchall()
            values = [(r["id"], r["fingerprint"], json.dumps(local_vector(r["content"])), now())
                      for r in rows if not SECRET.search(r["content"])]
            with conn:
                conn.executemany("INSERT OR REPLACE INTO memory_local_vectors VALUES(?,?,?,?)", values)
                conn.execute("DELETE FROM memory_local_vectors WHERE item_id NOT IN "
                             "(SELECT id FROM memory_items WHERE status='confirmed')")
                total = conn.execute("SELECT COUNT(*) FROM memory_local_vectors").fetchone()[0]
        return {"updated": len(values), "total": total}

    # -- 6. health ---------------------------------------------------------
    def health(self) -> dict:
        with closing(db.connection(self.path)) as conn:
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
        backup = None
        if check == "ok":
            backup = self.backup()
        return {"integrity": check, "backup": backup}

    def backup_dir(self) -> Path:
        return self.path.parent / "backups"

    def backup(self) -> str | None:
        """One consistent snapshot per day, last BACKUPS_KEPT kept.

        Forgetting a fact deletes these snapshots (see MemoryEngine.forget),
        so a backup never brings back something the user asked to forget.
        """
        folder = self.backup_dir()
        folder.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = folder / f"meiyuren-{day}.sqlite3"
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(temporary)) as dest:
                source.backup(dest)
            temporary.replace(target)
        snapshots = sorted(folder.glob("meiyuren-*.sqlite3"))
        for old in snapshots[:-BACKUPS_KEPT]:
            old.unlink(missing_ok=True)
        return target.name
