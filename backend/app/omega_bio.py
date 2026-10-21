"""OMEGA BIO: immutable, verifiable adaptive brain topology.

All changes are proposals until evaluated on an independent holdout.
No external calls, self-editing, data deletion, or unverified model training.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from hashlib import sha256
import json

MAX_EXPERTS=128
MAX_DEPTH=4

@dataclass(frozen=True)
class Expert:
    id: str
    parent: str
    topic: str
    sources: tuple[str,...]
    depth: int=1

@dataclass(frozen=True)
class Genome:
    experts: tuple[Expert,...]=()
    revision: int=0

    def digest(self) -> str:
        data=[(e.id,e.parent,e.topic,e.sources,e.depth) for e in self.experts]
        return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

class AdaptiveBrain:
    """Copy-on-write topology with an auditable local revision history."""
    def __init__(self, genome: Genome | None=None):
        self.current=genome or Genome()
        self.history=[self.current]
        self.proposals:dict[str,Genome]={}
        self.skills:dict[str,tuple[str,...]]={}

    def propose_growth(self, parent: str, topic: str, sources: set[str]) -> str:
        if len(sources)<3 or not topic.strip() or len(topic)>80:
            raise ValueError("Specialization needs three sources and bounded topic")
        if len(self.current.experts)>=MAX_EXPERTS:
            raise ValueError("Expert budget exceeded")
        parents={x.id:x for x in self.current.experts}
        if parent not in parents and parent not in ("knowledge","projects","goals",
                                                    "decisions","preferences","people",
                                                    "events","context"):
            raise ValueError("Unknown parent")
        depth=parents[parent].depth+1 if parent in parents else 1
        if depth>MAX_DEPTH:raise ValueError("Maximum expert depth")
        ident=sha256(f"{parent}|{topic}".encode()).hexdigest()[:16]
        if ident in parents: raise ValueError("Expert exists")
        expert=Expert(ident,parent,topic,tuple(sorted(sources)),depth)
        return self._stage(Genome(tuple(sorted((*self.current.experts,expert),
                                              key=lambda x:x.id)),
                                  self.current.revision+1))

    def propose_fusion(self, ids: tuple[str,str]) -> str:
        if len(set(ids))!=2: raise ValueError("Distinct experts required")
        items={e.id:e for e in self.current.experts}
        if any(i not in items for i in ids): raise ValueError("Unknown expert")
        left,right=(items[i] for i in ids)
        if left.parent!=right.parent: raise ValueError("Cannot merge across parents")
        topic=f"{left.topic}+{right.topic}"[:80]
        source_set=tuple(sorted(set(left.sources)|set(right.sources)))
        ident=sha256(f"{left.parent}|{topic}".encode()).hexdigest()[:16]
        remaining=[e for e in self.current.experts if e.id not in ids]
        if any(e.parent in ids for e in remaining):
            raise ValueError("Cannot merge experts with children")
        if ident in {e.id for e in remaining}: raise ValueError("Expert exists")
        remaining.append(Expert(ident,left.parent,topic,source_set,left.depth))
        return self._stage(Genome(tuple(sorted(remaining,key=lambda e:e.id)),
                                  self.current.revision+1))

    def propose_division(self, expert_id: str, partitions: dict[str,set[str]]) -> str:
        experts={e.id:e for e in self.current.experts}
        root=experts.get(expert_id)
        if not root:raise ValueError("Unknown expert")
        if root.depth>=MAX_DEPTH:raise ValueError("Maximum expert depth")
        children=[]
        for topic,sources in sorted(partitions.items()):
            if len(sources)<3 or not sources <= set(root.sources):
                raise ValueError("Division requires three original sources per child")
            ident=sha256(f"{root.id}|{topic}".encode()).hexdigest()[:16]
            if ident in experts or any(e.id==ident for e in children):
                raise ValueError("Duplicate specialization")
            children.append(Expert(ident,root.id,topic,tuple(sorted(sources)),root.depth+1))
        if len(children)<2 or len(self.current.experts)+len(children)>MAX_EXPERTS:
            raise ValueError("Division requires two children within budget")
        return self._stage(Genome(tuple(sorted((*self.current.experts,*children),
                                              key=lambda e:e.id)),
                                  self.current.revision+1))

    def _stage(self, candidate: Genome) -> str:
        key=candidate.digest()
        self.proposals[key]=candidate
        return key

    def evaluate_and_promote(self, key: str, baseline: list[bool],
                             trial: list[bool]) -> bool:
        from .omega import EvolutionArena
        candidate=self.proposals.get(key)
        if candidate is None:raise ValueError("Unknown candidate")
        outcome=EvolutionArena.compare(baseline,trial,minimum_cases=8)
        if not outcome["promote"]:return False
        if candidate.revision!=self.current.revision+1:
            raise ValueError("Stale candidate")
        self.current=candidate
        self.history.append(candidate)
        self.proposals.clear()
        return True

    def rollback(self) -> Genome:
        if len(self.history)<2: raise ValueError("No revision to restore")
        self.history.pop()
        self.current=self.history[-1]
        self.proposals.clear()
        return self.current

    def transfer_skill(self, name: str, source_expert: str,
                       target_expert: str, evidence: set[str]) -> dict:
        experts={e.id:e for e in self.current.experts}
        if source_expert not in experts or target_expert not in experts:
            raise ValueError("Unknown expert")
        if len(evidence)<3 or not evidence <= set(experts[source_expert].sources):
            raise ValueError("Transfer requires verified original evidence")
        return {"skill":name,"source":source_expert,"target":target_expert,
                "evidence":tuple(sorted(evidence)),"status":"proposed"}

    def diagnostics(self) -> dict:
        return {"revision":self.current.revision,"genome":self.current.digest(),
                "experts":len(self.current.experts),"pending":len(self.proposals),
                "history":len(self.history),"selfEdit":False}
