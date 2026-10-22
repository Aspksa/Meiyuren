"""v0.33 Cortex 3.0: meaning edges, cached graph, unified synapses, map API."""
from contextlib import closing
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import cloud, db
from backend.app.main import create_app
from backend.app.memory_engine import MemoryEngine
from backend.app.neural_cortex import Node, NeuralCortex
from backend.app.neural_synapses import SynapticStore


def unit(*values):
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm for v in values]


def test_long_facts_connect_by_smaller_fact():
    long_a = "Meiyuren Python архитектура интерфейс сервер база тесты сборка релиз документация"
    long_b = "Meiyuren Python бюджет команда встреча дизайн аватар музыка вечер прогулка"
    graph = NeuralCortex([Node("a", "projects", long_a, "m1"),
                          Node("b", "habits", long_b, "m2")])
    assert graph.diagnostics()["edges"] == 1
    assert graph.evidence[("a", "b")]["kind"] == "lexical"


def test_meaning_edge_without_shared_words():
    vectors = {"coffee": unit(1, 0.1, 0), "espresso": unit(1, 0.15, 0), "car": unit(0, 0, 1)}
    graph = NeuralCortex([Node("coffee", "habits", "Пью кофе по утрам", "m1"),
                          Node("espresso", "identity", "Обожаю эспрессо", "m2"),
                          Node("car", "projects", "Чиню машину", "m3")], vectors=vectors)
    assert graph.evidence[("coffee", "espresso")]["kind"] == "semantic"
    assert "car" not in graph.edges.get("coffee", {})
    assert graph.diagnostics()["semanticEdges"] == 1


def test_recall_never_walks_through_hidden_fact():
    graph = NeuralCortex([Node("a", "projects", "Meiyuren Python SQLite", "m1"),
                          Node("hidden", "knowledge", "Meiyuren Python SQLite React", "m2"),
                          Node("c", "goals", "React SQLite релиз", "m3")])
    every = {r["id"] for r in graph.recall("a", "global")}
    assert "hidden" in every
    visible = {r["id"] for r in graph.recall("a", "global", allowed={"a", "c"})}
    assert "hidden" not in visible


def test_recall_takes_strongest_path():
    graph = NeuralCortex([Node(i, b, "x", "m") for i, b in
                          (("s", "projects"), ("weak", "goals"), ("strong", "habits"), ("t", "knowledge"))])
    graph.edges.clear()
    for left, right, w in (("s", "weak", 0.9), ("weak", "t", 0.1),
                           ("s", "strong", 0.8), ("strong", "t", 0.9)):
        graph.edges[left][right] = graph.edges[right][left] = w
    best = {r["id"]: r for r in graph.recall("s", "global", depth=3)}
    # Через «strong» путь сильнее (0.8·0.9·0.85), чем через первый найденный «weak».
    assert best["t"]["via"] == "strong"
    assert best["t"]["score"] == pytest.approx(0.8 * 0.9 * 0.85, rel=1e-3)


def test_zeroed_synapses_are_deleted_and_do_not_fill_limit(tmp_path, monkeypatch):
    store = SynapticStore(tmp_path / "s.sqlite3")
    store.feedback("a", "b", True, eligible={"a", "b"})
    store.feedback("a", "b", False, eligible={"a", "b"})
    monkeypatch.setattr("backend.app.neural_synapses.MAX_PAIRS", 1)
    # Обнулённая пара не мешает новой.
    assert store.feedback("c", "d", True, eligible={"c", "d"}) == 0.05
    result = store.consolidate(eligible={"a", "b", "c", "d"}, force=True)
    assert result["cleared"] == 1
    with closing(store._open()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM neural_synapse_feedback").fetchone()[0] == 1


def test_apply_merges_fact_feedback_weights(tmp_path):
    path = tmp_path / "s.sqlite3"
    store = SynapticStore(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE memory_synaptic_weights(left_id TEXT,right_id TEXT,"
                     "adjustment REAL,observations INTEGER,updated_at INTEGER)")
        conn.execute("INSERT INTO memory_synaptic_weights VALUES('a','b',0.08,2,1)")
    store.feedback("a", "b", True, eligible={"a", "b"})
    graph = NeuralCortex([Node("a", "projects", "Meiyuren Python SQLite", "m1"),
                          Node("b", "knowledge", "Meiyuren Python SQLite", "m2")])
    assert store.apply(graph, eligible={"a", "b"}) == 1
    assert graph.feedback[("a", "b")] == pytest.approx(0.13)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud.keyring, "get_password", lambda *_: None)
    path = tmp_path / "cortex3.sqlite3"
    with TestClient(create_app(path), headers={"X-Meiyuren-Client": "1"}) as client:
        yield client, path


def seed_facts(client, path, facts):
    client.post("/api/chat/messages", json={"text": "Привет"})
    with closing(db.connection(path)) as conn:
        source = conn.execute("SELECT id FROM messages LIMIT 1").fetchone()[0]
        with conn:
            for i, (id_, brain, text) in enumerate(facts):
                conn.execute("""INSERT INTO memory_items
                    (id,content,fingerprint,kind,status,source_message_id,conversation_id,
                     cloud_allowed,created_at,updated_at,brain)
                    VALUES (?,?,?,'fact','confirmed',?,'global',0,?,?,?)""",
                             (id_, text, "fp" + id_, source, 1000 + i, 1000 + i, brain))


def test_graph_is_cached_and_survives_more_than_600_facts(app):
    client, path = app
    facts = [(f"f{i:04d}", ("projects", "knowledge")[i % 2], f"Meiyuren Python тема{i // 2}")
             for i in range(700)]
    seed_facts(client, path, facts)
    engine = MemoryEngine(path)
    first = engine.neural_cortex()
    assert first.diagnostics()["nodes"] == 700
    assert engine.neural_cortex() is first
    result = engine.deep_recall("Meiyuren Python тема3", "main", False)
    assert result


def test_map_node_card_and_synapse_feedback(app):
    client, path = app
    seed_facts(client, path, [("p", "projects", "Meiyuren Python SQLite интерфейс"),
                              ("k", "knowledge", "Meiyuren Python SQLite графы")])
    graph = client.get("/api/memory/universe/graph").json()
    cortex = [e for e in graph["edges"] if e["relation"] == "cortex"]
    assert cortex and cortex[0]["kind"] == "lexical"
    card = client.get("/api/memory/universe/nodes/p").json()
    assert card["item"]["content"].startswith("Meiyuren")
    assert card["links"][0]["id"] == "k" and card["links"][0]["terms"]
    before = card["links"][0]["weight"]
    response = client.post("/api/memory/universe/synapses",
                           json={"leftId": "p", "rightId": "k", "helpful": True})
    assert response.status_code == 200, response.text
    assert response.json()["weight"] > before
    assert client.post("/api/memory/universe/synapses",
                       json={"leftId": "p", "rightId": "missing", "helpful": True}).status_code == 422
    assert client.get("/api/memory/universe/nodes/missing").status_code == 404
    status = client.get("/api/memory/status").json()
    assert status["neuralCortex"]["edges"] == 1
    assert status["neuralCortex"]["learnedSynapses"] == 1


def test_snapshots_list_without_saving(app):
    client, _ = app
    assert client.get("/api/memory/universe/snapshots?save=false").json()["snapshots"] == []
    assert len(client.get("/api/memory/universe/snapshots").json()["snapshots"]) == 1
