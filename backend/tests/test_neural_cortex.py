from backend.app.neural_cortex import Node, NeuralCortex

def test_evidence_scope_and_cross_brain():
    nodes = [
        Node("p","projects","Meiyuren Python SQLite memory","msg1",scope="private-a"),
        Node("k","knowledge","Meiyuren Python SQLite architecture","msg2",scope="private-a"),
        Node("z","decisions","Meiyuren Python SQLite plans","msg3",scope="private-b"),
        Node("g","goals","Meiyuren Python SQLite roadmap","msg4",scope="global"),
        Node("bad","goals","Meiyuren Python SQLite roadmap","",scope="global"),
    ]
    graph=NeuralCortex(nodes)
    assert graph.diagnostics()["nodes"]==4
    assert "k" in {r["id"] for r in graph.recall("p","private-a")}
    assert "z" not in {r["id"] for r in graph.recall("p","private-a")}
    assert graph.recall("p","private-b")==[]
    assert "g" in {r["id"] for r in graph.recall("p","private-a")}

def test_feedback_bounded_and_pruning():
    graph=NeuralCortex([Node("a","projects","Meiyuren Python SQLite","a"),
                        Node("b","knowledge","Meiyuren Python SQLite","b")])
    assert graph.adjust("a","b",False)
    for _ in range(20):
        graph.adjust("a","b",False)
    assert -0.3 <= graph.feedback[("a","b")] <= 0.3
    assert graph.prune(0.99)==1
    assert graph.diagnostics()["edges"]==0

def test_never_invents_new_fact_or_crosses_scope():
    graph=NeuralCortex([Node("a","projects","Python SQLite Meiyuren","source-a"),
                        Node("b","knowledge","Python SQLite Meiyuren","source-b"),
                        Node("c","decisions","Python SQLite Meiyuren","source-c",confirmed=False)])
    result=graph.recall("a","global",depth=4)
    assert {r["id"] for r in result}=={"b"}
    assert all(r["source"] in {"source-a","source-b"} for r in result)
