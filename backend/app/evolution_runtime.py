"""Bounded, opt-in local evolution runtime for the existing eight-brain lab.

Runtime runs no remote research, shell commands, code edits, model downloads,
or paid inference. It only evaluates user-provided independent fixtures.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
from threading import Lock
from time import time
from . import cognitive_evolution as lab

MIN_INTERVAL = 6 * 3600

class EvolutionRuntime:
    def __init__(self, path: Path):
        self.path = path
        self._lock = Lock()

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return lab.connect(self.path)

    def status(self) -> dict:
        with closing(self._db()) as db:
            state = lab.status(db)
            setting = db.execute("SELECT value FROM evolution_state WHERE key='auto_enabled'").fetchone()
            last = db.execute("SELECT value FROM evolution_state WHERE key='last_run'").fetchone()
            state["automaticEvaluationEnabled"] = bool(setting and setting[0] == "1")
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
                enabled = db.execute("SELECT value FROM evolution_state WHERE key='auto_enabled'").fetchone()
                if not manual and (not enabled or enabled[0] != "1"):
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
