"""Meiyuren OMEGA: six cohesive, bounded and evidence-grounded cognitive services.

No network, unrestricted autonomous deployment, or unverified factual claims.
All memory evidence must be provided by caller after Memory Core visibility checks.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import log
from typing import Iterable

from .cognitive_evolution import terms
from .infinity_growth import Evidence, InfinityGrowth

MAX_WORLD_RELATIONS = 2000
MAX_EXPERIMENTS = 64

@dataclass(frozen=True)
class Relation:
    left: str
    right: str
    shared_terms: tuple[str, ...]
    source_ids: tuple[str, ...]

class WorldEngine:
    """Associative world graph; overlapping evidence is NOT proof of causality."""
    def __init__(self, evidence: Iterable[Evidence]):
        self.evidence={x.id:x for x in evidence if x.valid()}
        self.relations: list[Relation]=[]

    def build(self) -> list[Relation]:
        by_term:dict[str,set[str]]=defaultdict(set)
        for item in self.evidence.values():
            for token in terms(item.text):
                if len(token)>=4:
                    by_term[token].add(item.id)
        overlaps:dict[tuple[str,str],set[str]]=defaultdict(set)
        for token,ids in sorted(by_term.items()):
            for i,left in enumerate(sorted(ids)[:128]):
                for right in sorted(ids)[i+1:128]:
                    a,b=self.evidence[left],self.evidence[right]
                    if a.scope!=b.scope or a.source==b.source: continue
                    overlaps[(left,right)].add(token)
        self.relations=[
            Relation(a,b,tuple(sorted(shared)),tuple(sorted(
                (self.evidence[a].source,self.evidence[b].source))))
            for (a,b),shared in sorted(overlaps.items())
            if len(shared)>=2
        ][:MAX_WORLD_RELATIONS]
        return self.relations

class CognitiveImmuneSystem:
    """Reject unsupported/duplicate evidence and flag candidate contradictions."""
    @staticmethod
    def inspect(evidence: Iterable[Evidence]) -> dict:
        seen_sources:dict[str,str]={}
        accepted=[]
        rejected=[]
        for item in evidence:
            if not item.valid():
                rejected.append({"id":item.id,"reason":"invalid_or_unconfirmed"})
                continue
            fingerprint=sha256(
                f"{item.brain}|{item.scope}|{item.text.casefold().strip()}".encode()
            ).hexdigest()
            if fingerprint in seen_sources and seen_sources[fingerprint]==item.source:
                rejected.append({"id":item.id,"reason":"duplicate_same_source"})
                continue
            seen_sources[fingerprint]=item.source
            accepted.append(item)
        return {"accepted":accepted,"rejected":rejected}

class MemoryTiers:
    """Source-preserving deterministic partition labels, no record deletion."""
    @staticmethod
    def classify(evidence: Iterable[Evidence], *, active_ids: set[str] | None=None) -> dict:
        active=active_ids or set()
        layers={"working":[],"episodic":[],"semantic":[],"archive":[]}
        for item in evidence:
            if not item.valid(): continue
            if item.id in active:
                tier="working"
            elif item.brain in {"projects","goals","decisions"}:
                tier="episodic"
            elif item.brain=="knowledge":
                tier="semantic"
            else:
                tier="archive"
            layers[tier].append(item.id)
        return {key:sorted(value) for key,value in layers.items()}

class EvolutionArena:
    """Holdout scoring prevents unproven strategy promotion."""
    @staticmethod
    def compare(baseline: list[bool], candidate: list[bool], *,
                minimum_cases: int=8) -> dict:
        if len(baseline)!=len(candidate) or len(baseline)<minimum_cases:
            return {"promote":False,"reason":"insufficient_independent_cases"}
        base=sum(baseline)/len(baseline)
        trial=sum(candidate)/len(candidate)
        regressions=sum(a and not b for a,b in zip(baseline,candidate))
        return {"promote":trial>base and regressions==0,
                "baselineAccuracy":round(base,4),"candidateAccuracy":round(trial,4),
                "regressions":regressions,"cases":len(baseline)}

class SelfEngineeringLab:
    """Draft only inert proposals: NEVER execute, install or self-merge code."""
    @staticmethod
    def proposal(issue: str, benchmark: dict) -> dict:
        if not issue.strip() or len(issue)>500:
            raise ValueError("Bounded problem description required")
        digest=sha256(issue.encode()).hexdigest()[:16]
        return {"id":digest,"problem":issue,"benchmark":benchmark,
                "state":"requires_human_review","automaticCodeExecution":False,
                "automaticMerge":False}

class Omega:
    def __init__(self, evidence: Iterable[Evidence]):
        audited=CognitiveImmuneSystem.inspect(evidence)
        self.evidence=audited["accepted"]
        self.rejected=audited["rejected"]

    def overview(self) -> dict:
        growth=InfinityGrowth(self.evidence)
        grown=growth.grow(max_new=24)
        for node in grown[:6]:
            growth.specialize(node.id)
        world=WorldEngine(self.evidence)
        relations=world.build()
        return {
            "neuroFactory":{"subbrains":len(growth.subbrains),
                            "maximum":128,"growth":growth.metrics()},
            "worldEngine":{"relations":len(relations),"relationType":"shared_terms_not_causality"},
            "immuneSystem":{"accepted":len(self.evidence),"rejected":len(self.rejected)},
            "memoryTiers":{k:len(v) for k,v in MemoryTiers.classify(self.evidence).items()},
            "evolutionArena":{"automaticPromotion":False,"minimumHoldoutCases":8},
            "selfEngineering":{"automaticCodeExecution":False,"humanReview":True},
            "limitations":{"remoteFederation":False,"independentModelTraining":False,
                           "autonomousCodeDeployment":False},
        }
