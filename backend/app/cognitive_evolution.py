"""Offline cognitive evolution laboratory for Meiyuren.

No network, paid models, shell execution, or unreviewed source mutation.
Experiments use sealed fixtures and are only promoted after holdout evaluation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict
import argparse
import hashlib
import json
import os
import re
import sqlite3
from typing import Iterable

BRAINS = ("identity", "episodes", "goals", "habits", "knowledge",
          "relationships", "projects", "decisions")
WORD = re.compile(r"[^\W_]+", re.UNICODE)
MAX_EVIDENCE = 2000
MAX_FIXTURES = 512
STRATEGIES = {"balanced": (1.0, 0.2), "focused": (1.4, 0.0),
              "context": (0.8, 0.5)}
STOP = {"это", "моя", "мое", "для", "как", "или", "the", "and", "with"}


def terms(text: str) -> set[str]:
    return {w.casefold() for w in WORD.findall(text) if len(w) >= 3 and
            w.casefold() not in STOP}


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS evolution_evidence (
       id TEXT PRIMARY KEY, brain TEXT NOT NULL, title TEXT NOT NULL,
       content TEXT NOT NULL, source_uri TEXT NOT NULL,
       observed_at TEXT NOT NULL, trust TEXT NOT NULL,
       consent_cloud INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS evolution_fixtures (
       id TEXT PRIMARY KEY, query TEXT NOT NULL, expected_id TEXT NOT NULL,
       split TEXT NOT NULL CHECK(split IN ('train','holdout')));
    CREATE TABLE IF NOT EXISTS evolution_candidates (
       id TEXT PRIMARY KEY, strategy TEXT NOT NULL, train_hits INTEGER NOT NULL,
       train_total INTEGER NOT NULL, holdout_hits INTEGER NOT NULL,
       holdout_total INTEGER NOT NULL, promoted INTEGER NOT NULL,
       evaluated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS evolution_state (
       key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS evolution_proposals (
       id TEXT PRIMARY KEY, kind TEXT NOT NULL, proposal TEXT NOT NULL,
       status TEXT NOT NULL CHECK(status IN ('pending','reviewed','rejected')),
       created_at TEXT NOT NULL);
    """)
    return db


@dataclass(frozen=True)
class Evidence:
    brain: str
    title: str
    content: str
    source_uri: str
    observed_at: str
    trust: str = "unverified"
    consent_cloud: bool = False

    def validate(self) -> None:
        if self.brain not in BRAINS:
            raise ValueError("Unknown brain")
        if self.trust not in ("unverified", "source_checked", "independent"):
            raise ValueError("Invalid trust")
        if not self.source_uri or len(self.source_uri) > 1000:
            raise ValueError("Evidence requires provenance")
        if any(len(v) > 4000 for v in (self.title, self.content)):
            raise ValueError("Oversized evidence")
        datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))


def register_evidence(db: sqlite3.Connection, item: Evidence) -> str:
    item.validate()
    digest = hashlib.sha256(json.dumps(asdict(item), sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    with db:
        count = db.execute("SELECT COUNT(*) FROM evolution_evidence").fetchone()[0]
        exists = db.execute("SELECT 1 FROM evolution_evidence WHERE id=?", (digest,)).fetchone()
        if count >= MAX_EVIDENCE and not exists:
            raise ValueError("Evidence capacity reached")
        db.execute("""INSERT OR IGNORE INTO evolution_evidence
                     (id,brain,title,content,source_uri,observed_at,trust,consent_cloud)
                     VALUES(?,?,?,?,?,?,?,?)""",
                   (digest, item.brain, item.title, item.content,
                    item.source_uri, item.observed_at, item.trust, int(item.consent_cloud)))
    return digest


def register_fixture(db: sqlite3.Connection, query: str, expected_id: str,
                     split: str = "holdout") -> str:
    if split not in ("train", "holdout") or not 2 <= len(query) <= 500:
        raise ValueError("Invalid fixture")
    if not db.execute("SELECT 1 FROM evolution_evidence WHERE id=?", (expected_id,)).fetchone():
        raise ValueError("Expected evidence does not exist")
    digest = hashlib.sha256((split + "\0" + query + "\0" + expected_id).encode()).hexdigest()
    with db:
        count = db.execute("SELECT COUNT(*) FROM evolution_fixtures").fetchone()[0]
        exists = db.execute("SELECT 1 FROM evolution_fixtures WHERE id=?", (digest,)).fetchone()
        if count >= MAX_FIXTURES and not exists:
            raise ValueError("Fixture capacity reached")
        db.execute("INSERT OR IGNORE INTO evolution_fixtures VALUES(?,?,?,?)",
                   (digest, query, expected_id, split))
    return digest


def retrieve(rows: Iterable[sqlite3.Row], query: str, strategy: str,
             limit: int = 3) -> list[str]:
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy")
    token_weight, trust_weight = STRATEGIES[strategy]
    q = terms(query)
    scored = []
    for row in rows:
        overlap = len(q & terms(row["title"] + " " + row["content"]))
        if not overlap:
            continue
        trust = {"unverified": 0, "source_checked": 1, "independent": 2}[row["trust"]]
        score = token_weight * overlap + trust_weight * trust
        scored.append((-score, row["id"]))
    return [id_ for _, id_ in sorted(scored)[:limit]]


def evaluation(db: sqlite3.Connection, strategy: str, split: str) -> tuple[int, int]:
    rows = db.execute("SELECT * FROM evolution_evidence ORDER BY id").fetchall()
    fixtures = db.execute("SELECT * FROM evolution_fixtures WHERE split=? ORDER BY id",
                          (split,)).fetchall()
    hits = sum(f["expected_id"] in retrieve(rows, f["query"], strategy)
               for f in fixtures)
    return hits, len(fixtures)


def evolve(db: sqlite3.Connection) -> dict:
    """Choose by training evidence, only promote if sealed holdout improves baseline.

    Holdout is used once per invocation for final gate, not to choose strategy.
    Minimum 5 holdout cases prevent promotions on tiny samples.
    """
    train = {s: evaluation(db, s, "train") for s in STRATEGIES}
    active_row = db.execute("SELECT value FROM evolution_state WHERE key='strategy'").fetchone()
    active = active_row["value"] if active_row else "balanced"
    winner = sorted(STRATEGIES, key=lambda s: (-train[s][0], s != active, s))[0]
    base_hits, n = evaluation(db, active, "holdout")
    new_hits, _ = evaluation(db, winner, "holdout")
    promoted = n >= 5 and train[winner][1] >= 3 and new_hits > base_hits
    timestamp = datetime.now(timezone.utc).isoformat()
    experiment_id = hashlib.sha256((winner + timestamp).encode()).hexdigest()
    with db:
        db.execute("INSERT INTO evolution_candidates VALUES(?,?,?,?,?,?,?,?)",
                   (experiment_id, winner, *train[winner], new_hits, n,
                    int(promoted), timestamp))
        if promoted:
            db.execute("INSERT OR REPLACE INTO evolution_state VALUES('strategy',?)",
                       (winner,))
    return {"candidate": winner, "active": winner if promoted else active,
            "trainHits": train[winner][0], "trainCases": train[winner][1],
            "baselineHoldoutHits": base_hits, "candidateHoldoutHits": new_hits,
            "holdoutCases": n, "promoted": promoted}


def specializations(db: sqlite3.Connection) -> list[dict]:
    """Derive bounded topical subbrains from sourced evidence, without creating facts."""
    rows = db.execute("SELECT brain,title,content FROM evolution_evidence").fetchall()
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        for token in terms(row["title"]):
            counts[row["brain"]][token] += 1
    return [{"brain": brain, "topics": [{"name": term, "evidenceCount": count}
            for term, count in counts[brain].most_common(8) if count >= 2]}
            for brain in BRAINS]


def status(db: sqlite3.Connection) -> dict:
    counts = {name: db.execute("SELECT COUNT(*) FROM " + name).fetchone()[0] for name in
              ("evolution_evidence", "evolution_fixtures", "evolution_candidates",
               "evolution_proposals")}
    active = db.execute("SELECT value FROM evolution_state WHERE key='strategy'").fetchone()
    return {"brains": len(BRAINS), "strategy": active[0] if active else "balanced",
            "counts": counts, "specializations": specializations(db),
            "externalResearchEnabled": False, "autoCodeExecution": False,
            "autoDeployment": False}


def propose_change(db: sqlite3.Connection, kind: str, proposal: str) -> str:
    """Record a reviewable change proposal; never writes repository source files."""
    if kind not in ("code", "model", "research") or not 5 <= len(proposal) <= 8000:
        raise ValueError("Invalid proposal")
    stamp = datetime.now(timezone.utc).isoformat()
    id_ = hashlib.sha256((kind + "\0" + proposal).encode()).hexdigest()
    with db:
        db.execute("INSERT OR IGNORE INTO evolution_proposals VALUES(?,?,?,?,?)",
                   (id_, kind, proposal, "pending", stamp))
    return id_


def main() -> None:
    parser = argparse.ArgumentParser(description="Meiyuren offline evolution lab")
    parser.add_argument("--db", type=Path, default=Path("data/cognitive_evolution.sqlite3"))
    parser.add_argument("command", choices=("status", "evolve", "import-evidence", "add-fixture", "propose"))
    parser.add_argument("--json", help="JSON object for import-evidence, add-fixture or propose")
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = connect(args.db)
    try:
        if args.command == "status":
            result = status(db)
        elif args.command == "evolve":
            result = evolve(db)
        else:
            if not args.json:
                parser.error("--json is required")
            payload = json.loads(args.json)
            if args.command == "import-evidence":
                result = {"id": register_evidence(db, Evidence(**payload))}
            elif args.command == "add-fixture":
                result = {"id": register_fixture(db, **payload)}
            else:
                result = {"id": propose_change(db, **payload)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
