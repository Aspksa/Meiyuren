"""Offline checks for cognitive evolution laboratory."""
from datetime import datetime, timezone
from backend.app.cognitive_evolution import (
    BRAINS, Evidence, connect, register_evidence, register_fixture,
    retrieve, evolve, status, specializations, propose_change
)
import pytest


def evidence(brain, title, trust="source_checked"):
    return Evidence(brain, title, title + " reproducible notes",
                    "local:test/" + brain + "/" + title.replace(" ", "-"),
                    datetime.now(timezone.utc).isoformat(), trust)


def test_provenance_and_brain_scope(tmp_path):
    db = connect(tmp_path / "lab.sqlite3")
    with pytest.raises(ValueError):
        register_evidence(db, evidence("nonexistent", "test knowledge"))
    item = evidence("projects", "Meiyuren memory system")
    item_id = register_evidence(db, item)
    assert register_evidence(db, item) == item_id
    assert status(db)["counts"]["evolution_evidence"] == 1
    assert status(db)["brains"] == len(BRAINS) == 8
    assert status(db)["externalResearchEnabled"] is False
    db.close()


def test_holdout_gate_and_no_unearned_promotion(tmp_path):
    db = connect(tmp_path / "lab.sqlite3")
    for i in range(8):
        id_ = register_evidence(db, evidence("knowledge", "python project " + str(i)))
        register_fixture(db, "python project " + str(i), id_, "holdout")
    result = evolve(db)
    assert result["promoted"] is False
    assert result["active"] == "balanced"
    assert result["holdoutCases"] == 8
    assert status(db)["counts"]["evolution_candidates"] == 1
    db.close()


def test_review_proposals_never_change_files(tmp_path):
    db = connect(tmp_path / "lab.sqlite3")
    code = tmp_path / "source.py"
    code.write_text("original", encoding="utf-8")
    proposal = propose_change(db, "code", "Change source.py into a better implementation")
    assert db.execute("SELECT status FROM evolution_proposals WHERE id=?",
                      (proposal,)).fetchone()[0] == "pending"
    assert code.read_text(encoding="utf-8") == "original"
    with pytest.raises(ValueError):
        propose_change(db, "shell", "execute arbitrary commands")
    db.close()


def test_specializations_require_repeated_evidence(tmp_path):
    db = connect(tmp_path / "lab.sqlite3")
    register_evidence(db, evidence("projects", "Meiyuren knowledge"))
    register_evidence(db, evidence("projects", "Meiyuren architecture"))
    topics = next(s["topics"] for s in specializations(db) if s["brain"] == "projects")
    assert any(t["name"] == "meiyuren" and t["evidenceCount"] == 2 for t in topics)
    db.close()


def test_no_retrieval_without_token_overlap(tmp_path):
    db = connect(tmp_path / "lab.sqlite3")
    register_evidence(db, evidence("knowledge", "Python workflows"))
    rows = db.execute("SELECT * FROM evolution_evidence").fetchall()
    assert retrieve(rows, "astronomy telescopes", "balanced") == []
    db.close()
