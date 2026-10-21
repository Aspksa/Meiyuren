"""Bounded local evolution runtime for the existing eight-brain lab.

Runtime runs no remote research, shell commands, code edits, model downloads,
or paid inference. Fixtures come automatically from the user's own ratings of
memories used in chat answers ("вопрос → полезный факт"), synced on each tick.
Enabled by default; the user can switch it off.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone
import hashlib
from time import time
from . import cognitive_evolution as lab

MIN_INTERVAL = 6 * 3600

class EvolutionRuntime:
    def __init__(self, path: Path, memory=None):
        self.path = path
        # Optional MemoryEngine: source of live user ratings and forget-propagation.
        self.memory = memory
        self._synced: str | None = None
        self._lock = Lock()

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return lab.connect(self.path)

    def status(self) -> dict:
        with closing(self._db()) as db:
            state = lab.status(db)
            setting = db.execute("SELECT value FROM evolution_state WHERE key='auto_enabled'").fetchone()
            last = db.execute("SELECT value FROM evolution_state WHERE key='last_run'").fetchone()
            state["automaticEvaluationEnabled"] = not setting or setting[0] == "1"
            state["lastEvaluationAt"] = int(last[0]) if last else None
            state["nextEligibleAt"] = (int(last[0]) + MIN_INTERVAL) if last else None
            state["independentFixtureRequired"] = True
            return state

    def set_enabled(self, enabled: bool) -> dict:
        with self._lock, closing(self._db()) as db:
            with db:
                db.execute("INSERT OR REPLACE INTO evolution_state VALUES('auto_enabled',?)",
                           ("1" if enabled else "0",))
        return self.status()

    def tick(self, *, manual: bool = False) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"ran": False, "reason": "busy"}
        try:
            with closing(self._db()) as db:
                if self.memory is not None:
                    # Дёшево: работает, только когда оценки изменились. Забытые
                    # воспоминания удаляются из лаборатории даже при выключенной эволюции.
                    self.sync(db)
                enabled = db.execute("SELECT value FROM evolution_state WHERE key='auto_enabled'").fetchone()
                if not manual and enabled and enabled[0] != "1":
                    return {"ran": False, "reason": "disabled"}
                last = db.execute("SELECT value FROM evolution_state WHERE key='last_run'").fetchone()
                stamp = int(time())
                if not manual and last and stamp-int(last[0]) < MIN_INTERVAL:
                    return {"ran": False, "reason": "interval"}
                train = db.execute("SELECT COUNT(*) FROM evolution_fixtures WHERE split='train'").fetchone()[0]
                holdout = db.execute("SELECT COUNT(*) FROM evolution_fixtures WHERE split='holdout'").fetchone()[0]
                if train < 3 or holdout < 5:
                    return {"ran": False, "reason": "insufficient_independent_fixtures",
                            "trainCases": train, "holdoutCases": holdout}
                result = lab.evolve(db)
                with db:
                    db.execute("INSERT OR REPLACE INTO evolution_state VALUES('last_run',?)", (str(stamp),))
                return {"ran": True, **result}
        finally:
            self._lock.release()

    def sync(self, db) -> dict:
        """Mirror live rated memories into the lab; drop anything forgotten.

        Lab evidence is a text copy, so a memory deleted in Memory Core must
        disappear here on the very next tick together with its fixtures.
        """
        judgments = self.memory.relevance_judgments()
        signature = hashlib.sha256("\0".join(
            sorted(j["memoryId"] + "|" + j["query"] for j in judgments)).encode()).hexdigest()
        if signature == self._synced:
            return {"synced": 0, "removed": 0}
        live = {j["memoryId"] for j in judgments}
        uri = "meiyuren:memory/"
        removed = 0
        with db:
            for row in db.execute("SELECT id,source_uri FROM evolution_evidence "
                                  "WHERE source_uri LIKE 'meiyuren:memory/%'").fetchall():
                if row["source_uri"][len(uri):] not in live:
                    db.execute("DELETE FROM evolution_fixtures WHERE expected_id=?", (row["id"],))
                    db.execute("DELETE FROM evolution_evidence WHERE id=?", (row["id"],))
                    removed += 1
        added = 0
        for j in judgments:
            observed = datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).isoformat()
            try:
                evidence = lab.register_evidence(db, lab.Evidence(
                    j["brain"], j["content"][:80], j["content"], uri + j["memoryId"],
                    observed, "source_checked"))
                # Stable split: roughly a third of cases become sealed holdout.
                split = "holdout" if int(hashlib.sha256(
                    (j["query"] + j["memoryId"]).encode()).hexdigest(), 16) % 3 == 0 else "train"
                lab.register_fixture(db, j["query"][:500], evidence, split)
                added += 1
            except ValueError:
                continue
        self._synced = signature
        return {"synced": added, "removed": removed}
