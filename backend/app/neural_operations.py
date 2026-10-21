"""Autonomous, local-only Neural Operations control plane.

Safety invariants: whole-database source eligibility for pruning, no network,
no paid inference, no self-editing, no privacy-scope mixing, no implicit
positive feedback and no claiming benchmark accuracy without labeled cases.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import sqlite3
import threading
import time

from . import db
from .neural_synapses import SynapticStore

class NeuralOperations:
    def __init__(self, path: Path):
        self.path = path
        self.store = SynapticStore(path)
        self.lock = threading.Lock()

    def _eligible(self) -> set[str]:
        # Deliberately scan ALL eligible records: recall's 600-node bound must
        # never cause valid but unindexed memories to lose their learned weights.
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute("""
                SELECT i.id FROM memory_items i
                WHERE i.status='confirmed'
                AND (i.expires_at IS NULL OR i.expires_at>?)
                AND i.source_message_id IS NOT NULL
                AND EXISTS (SELECT 1 FROM messages m WHERE m.id=i.source_message_id)
                """, (int(time.time()*1000),)).fetchall()  # expires_at в миллисекундах
        return {r["id"] for r in rows}

    def status(self) -> dict:
        with closing(self.store._open()) as conn:
            n=conn.execute("SELECT COUNT(*) FROM neural_synapse_feedback").fetchone()[0]
            stamp=conn.execute("SELECT value FROM neural_synapse_state WHERE name='last_consolidation'").fetchone()
            runs=conn.execute("SELECT value FROM neural_synapse_state WHERE name='completed_runs'").fetchone()
        return {"synapses":n, "lastConsolidatedAt":stamp[0] if stamp else None,
                "completedRuns":runs[0] if runs else 0,
                "intervalSeconds":21600, "automaticMaintenance":True,
                "externalCalls":False, "codeModification":False}

    def tick(self, force: bool=False) -> dict:
        if not self.lock.acquire(blocking=False):
            return {"ran":False, "reason":"busy"}
        try:
            eligible=self._eligible()
            outcome=self.store.consolidate(eligible=eligible,force=force)
            if outcome["ran"]:
                with closing(self.store._open()) as conn:
                    with conn:
                        conn.execute("""INSERT INTO neural_synapse_state VALUES('completed_runs',1)
                            ON CONFLICT(name) DO UPDATE SET value=value+1""")
            return {**outcome,"eligible":len(eligible)}
        finally:
            self.lock.release()
