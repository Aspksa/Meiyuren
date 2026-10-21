"""OMEGA six-component deterministic and safety regression tests."""
import pytest
from backend.app.infinity_growth import Evidence
from backend.app.omega import (Omega,WorldEngine,MemoryTiers,
    CognitiveImmuneSystem,EvolutionArena,SelfEngineeringLab)

def corpus():
    return [
        Evidence(f"p{i}","projects","meiyuren python memory neural learning",
                 f"source-{i}",scope="main")
        for i in range(4)
    ]+[Evidence("k1","knowledge","meiyuren python memory neural learning",
                "source-k",scope="main")]

def test_world_relations_have_two_distinct_sources_and_no_claimed_causality():
    relationships=WorldEngine(corpus()).build()
    assert relationships
    assert all(len(r.shared_terms)>=2 and r.source_ids[0]!=r.source_ids[1]
               for r in relationships)
    assert Omega(corpus()).overview()["worldEngine"]["relationType"]=="shared_terms_not_causality"

def test_immune_rejects_unconfirmed_but_not_independent_sources():
    rows=corpus()+[Evidence("bad","projects","unverified","",confirmed=True),
                   Evidence("duplicate","projects",corpus()[0].text,
                            corpus()[0].source,scope="main")]
    inspected=CognitiveImmuneSystem.inspect(rows)
    assert {r["id"] for r in inspected["rejected"]}=={"bad","duplicate"}
    assert len(inspected["accepted"])==5

def test_neurofactory_memory_tiers_and_boundaries():
    report=Omega(corpus()).overview()
    assert report["neuroFactory"]["subbrains"]>0
    assert report["memoryTiers"]["episodic"]==4
    assert report["memoryTiers"]["semantic"]==1
    assert report["selfEngineering"]["humanReview"] is True

def test_evolution_arena_never_promotes_without_clean_holdout():
    assert EvolutionArena.compare([True]*4,[True]*4)["promote"] is False
    baseline=[False]*8
    candidate=[True]*8
    assert EvolutionArena.compare(baseline,candidate)["promote"] is True
    baseline=[True]+[False]*7
    candidate=[False]+[True]*7
    assert EvolutionArena.compare(baseline,candidate)["promote"] is False

def test_engineering_lab_never_executes():
    assert SelfEngineeringLab.proposal("Improve recall",{})["automaticMerge"] is False
    with pytest.raises(ValueError):
        SelfEngineeringLab.proposal("",{})
