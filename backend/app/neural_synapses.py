"""Local, bounded persisted synaptic evidence.

Does not retain user text. Edges are eligible only while both source-backed
memory records remain visible. Forgetting removes both weight and evidence.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import sqlite3
import time

MAX_ADJUSTMENT = 0.3
MAX_PAIRS = 1200
MIN_INTERVAL = 6 * 3600

class SynapticStore:
    def __init__(self, path: Path):
        self.path = path

    def _open(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("""CREATE TABLE IF NOT EXISTS neural_synapse_feedback(
            left_id TEXT NOT NULL, right_id TEXT NOT NULL,
            adjustment REAL NOT NULL DEFAULT 0,
            useful INTEGER NOT NULL DEFAULT 0,
            harmful INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY(left_id,right_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS neural_synapse_state(
            name TEXT PRIMARY KEY, value INTEGER NOT NULL)""")
        return db

    @staticmethod
    def pair(left: str, right: str) -> tuple[str, str]:
        if not left or not right or left == right:
            raise ValueError("Two different memory IDs required")
        return tuple(sorted((left, right)))

    def feedback(self, left: str, right: str, helpful: bool,
                 *, eligible: set[str]) -> float:
        a, b = self.pair(left, right)
        if not {a, b} <= eligible:
            raise ValueError("Both source-backed memories must be visible")
        with closing(self._open()) as conn:
            with conn:
                row = conn.execute("SELECT adjustment,useful,harmful FROM neural_synapse_feedback WHERE left_id=? AND right_id=?",
                                   (a,b)).fetchone()
                if row is None and conn.execute("SELECT COUNT(*) FROM neural_synapse_feedback").fetchone()[0] >= MAX_PAIRS:
                    raise ValueError("Synapse limit reached")
                old = float(row[0]) if row else 0
                new = round(max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT,
                                old + (0.05 if helpful else -0.05))), 4)
                conn.execute("""INSERT INTO neural_synapse_feedback VALUES(?,?,?,?,?,?)
                    ON CONFLICT(left_id,right_id) DO UPDATE SET
                    adjustment=excluded.adjustment,useful=excluded.useful,
                    harmful=excluded.harmful,updated_at=excluded.updated_at""",
                    (a,b,new,(row[1] if row else 0)+int(helpful),
                     (row[2] if row else 0)+int(not helpful),int(time.time())))
        return new

    def apply(self, cortex, *, eligible: set[str]) -> int:
        applied=0
        with closing(self._open()) as conn:
            rows=conn.execute("SELECT left_id,right_id,adjustment FROM neural_synapse_feedback").fetchall()
        for a,b,adjustment in rows:
            if a in eligible and b in eligible and b in cortex.edges.get(a,{}):
                cortex.feedback[(a,b)] = max(-MAX_ADJUSTMENT,min(MAX_ADJUSTMENT,float(adjustment)))
                applied+=1
        return applied

    def consolidate(self, *, eligible: set[str], force: bool = False) -> dict:
        """Remove orphaned edges and gradually decay unused weights.

        Run after caller establishes the complete eligible source set.
        It never adds a fact or reinforces a link without explicit feedback.
        """
        now=int(time.time())
        with closing(self._open()) as conn:
            with conn:
                last=conn.execute("SELECT value FROM neural_synapse_state WHERE name='last_consolidation'").fetchone()
                if last and not force and now-last[0]<MIN_INTERVAL:
                    return {"ran":False,"reason":"interval"}
                rows=conn.execute("SELECT left_id,right_id,adjustment FROM neural_synapse_feedback").fetchall()
                purged=decayed=0
                for a,b,value in rows:
                    if a not in eligible or b not in eligible:
                        conn.execute("DELETE FROM neural_synapse_feedback WHERE left_id=? AND right_id=?",(a,b))
                        purged+=1
                    else:
                        adjusted=round(float(value)*0.98,4)
                        if abs(adjusted)<0.005:
                            adjusted=0.0
                        conn.execute("UPDATE neural_synapse_feedback SET adjustment=? WHERE left_id=? AND right_id=?",
                                     (adjusted,a,b))
                        decayed+=1
                conn.execute("INSERT OR REPLACE INTO neural_synapse_state VALUES('last_consolidation',?)",(now,))
        return {"ran":True,"purged":purged,"decayed":decayed}
