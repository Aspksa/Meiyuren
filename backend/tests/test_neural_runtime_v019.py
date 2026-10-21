"""v0.19 live Neural Cortex recall integration regression."""
from backend.app.memory_engine import MemoryEngine
from backend.app.neural_cortex import NeuralCortex, Node


def test_neural_candidate_requires_source_and_live_visibility(tmp_path, monkeypatch):
    engine = MemoryEngine(tmp_path / "unused.sqlite3")
    rows = [
        {"id": "p", "brain": "projects", "content": "Meiyuren Python SQLite",
         "sourceMessageId": "source-p"},
        {"id": "k", "brain": "knowledge", "content": "Meiyuren Python SQLite",
         "sourceMessageId": "source-k"},
        {"id": "private", "brain": "decisions", "content": "Meiyuren Python SQLite",
         "sourceMessageId": None},
    ]
    # Mocking the ACL-filtered interface simulates a visible local conversation;
    # no unseen item may be inserted into the graph.
    monkeypatch.setattr(engine, "_visible_deep_rows", lambda *_: rows)
    sourced = [r for r in engine._visible_deep_rows("main", False)
               if r.get("sourceMessageId")]
    graph = NeuralCortex(Node(id=r["id"], brain=r["brain"], text=r["content"],
                              source=r["sourceMessageId"]) for r in sourced)
    hits = graph.recall("p", "global")
    assert {h["id"] for h in hits} == {"k"}
    assert all(h["source"] == "source-k" for h in hits)


def test_neural_api_is_pure_local_graph():
    graph = NeuralCortex([Node("a", "projects", "Python Meiyuren SQLite", "message-a"),
                          Node("b", "knowledge", "Python Meiyuren SQLite", "message-b")])
    before = graph.diagnostics()
    assert before["edges"] == 1
    assert graph.adjust("a", "b", True)
    assert graph.diagnostics()["edges"] == before["edges"]
