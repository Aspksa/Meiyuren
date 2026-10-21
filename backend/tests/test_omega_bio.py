"""OMEGA BIO single-module regression: growth, division, fusion, promotion, rollback."""
from backend.app.omega_bio import AdaptiveBrain
import pytest

def test_growth_holdout_and_rollback():
    brain=AdaptiveBrain()
    key=brain.propose_growth("knowledge","python neural",{"s1","s2","s3","s4"})
    assert brain.diagnostics()["experts"]==0
    assert brain.evaluate_and_promote(key,[False]*8,[True]*8)
    assert brain.diagnostics()["experts"]==1
    assert brain.rollback().revision==0

def test_division_and_fusion():
    brain=AdaptiveBrain()
    key=brain.propose_growth("knowledge","research",{"a","b","c","d"})
    assert brain.evaluate_and_promote(key,[False]*8,[True]*8)
    root=brain.current.experts[0]
    key=brain.propose_division(root.id,{"math":{"a","b","c"},
                                            "physics":{"b","c","d"}})
    assert brain.evaluate_and_promote(key,[False]*8,[True]*8)
    children=[e for e in brain.current.experts if e.parent==root.id]
    assert len(children)==2
    transfer=brain.transfer_skill("calibration",children[0].id,children[1].id,
                                   set(children[0].sources))
    assert transfer["status"]=="proposed"
    key=brain.propose_fusion((children[0].id,children[1].id))
    assert brain.evaluate_and_promote(key,[False]*8,[True]*8)
    assert len(brain.current.experts)==2

def test_unverified_promotions_rejected():
    brain=AdaptiveBrain()
    with pytest.raises(ValueError):
        brain.propose_growth("knowledge","weak",{"one"})
    key=brain.propose_growth("knowledge","verified",{"1","2","3"})
    assert brain.evaluate_and_promote(key,[True]*8,[False]*8) is False
    assert brain.diagnostics()["experts"]==0
    with pytest.raises(ValueError):
        brain.rollback()
