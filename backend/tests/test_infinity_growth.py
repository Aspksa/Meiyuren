"""Infinity Growth privacy, reproducibility, recursion and partition tests."""
import pytest
from backend.app.infinity_growth import Evidence, InfinityGrowth

def items():
    return [
        Evidence("p1","projects","Meiyuren python neural memory","s1",scope="local"),
        Evidence("p2","projects","Meiyuren python neural memory","s2",scope="local"),
        Evidence("p3","projects","Meiyuren python neural memory","s3",scope="local"),
        Evidence("p4","projects","Meiyuren python neural memory","s4",scope="global"),
        Evidence("wrong","projects","Meiyuren python neural memory","",scope="local"),
        Evidence("rejected","projects","Meiyuren python neural memory","s5",scope="local",confirmed=False),
    ]

def test_growth_requires_independent_provenance_and_scope():
    growth=InfinityGrowth(items())
    assert len(growth.memories)==4
    nodes=growth.grow(minimum_sources=3,max_new=8)
    assert nodes
    assert all(node.parent=="projects" and node.depth==1 for node in nodes)
    assert all("wrong" not in node.evidence_ids for node in nodes)
    assert all("p4" not in node.evidence_ids for node in nodes)
    assert growth.grow(minimum_sources=3)==[]

def test_recursion_is_bounded_and_reproducible():
    growth=InfinityGrowth(items())
    root=growth.grow(max_new=1)[0]
    children=growth.specialize(root.id)
    assert all(child.parent==root.id and child.depth==2 for child in children)
    assert growth.specialize(root.id)==[]
    assert root.id==InfinityGrowth(items()).grow(max_new=1)[0].id

def test_shard_plan_stable_complete_and_local():
    growth=InfinityGrowth(items())
    first=growth.distribute(8)
    assert first==growth.distribute(8)
    assert sorted(id_ for group in first.values() for id_ in group)==sorted(growth.memories)
    with pytest.raises(ValueError):
        growth.distribute(33)
    assert growth.metrics()["remoteExecution"] is False

def test_curiosity_questions_not_confused_with_verified_claims():
    growth=InfinityGrowth([Evidence("one","knowledge","quantum astronomy telescope","s1")])
    questions=growth.questions()
    assert questions
    assert all(q["sources"]==1 and q["question"].endswith("?") for q in questions)
