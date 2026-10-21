"""Regression for persisted source-scoped synaptic plasticity and cleanup."""
import pytest
from backend.app.neural_synapses import SynapticStore
from backend.app.neural_cortex import Node, NeuralCortex


def graph():
    return NeuralCortex([Node("a","projects","Meiyuren Python SQLite","source-a"),
                         Node("b","knowledge","Meiyuren Python SQLite","source-b")])


def test_feedback_requires_both_visible_sources(tmp_path):
    store=SynapticStore(tmp_path/"memory.sqlite3")
    with pytest.raises(ValueError):
        store.feedback("a","b",True,eligible={"a"})
    assert store.feedback("a","b",True,eligible={"a","b"})==0.05
    assert store.apply(graph(),eligible={"a"})==0
    cortex=graph()
    assert store.apply(cortex,eligible={"a","b"})==1
    assert cortex.feedback[("a","b")]==0.05


def test_feedback_bounds_and_source_forgetting(tmp_path):
    store=SynapticStore(tmp_path/"memory.sqlite3")
    for _ in range(15):
        store.feedback("a","b",True,eligible={"a","b"})
    cortex=graph()
    store.apply(cortex,eligible={"a","b"})
    assert cortex.feedback[("a","b")]==0.3
    result=store.consolidate(eligible={"a"},force=True)
    assert result["purged"]==1
    assert store.apply(graph(),eligible={"a","b"})==0


def test_consolidation_idempotent_interval_and_decay(tmp_path):
    store=SynapticStore(tmp_path/"memory.sqlite3")
    store.feedback("a","b",False,eligible={"a","b"})
    first=store.consolidate(eligible={"a","b"},force=True)
    assert first["ran"] and first["decayed"]==1
    assert store.consolidate(eligible={"a","b"})["reason"]=="interval"
    cortex=graph()
    store.apply(cortex,eligible={"a","b"})
    assert -0.05<cortex.feedback[("a","b")]<0
