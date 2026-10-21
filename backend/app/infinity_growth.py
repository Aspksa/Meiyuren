"""Meiyuren Infinity Growth: bounded neurogenesis, recursive brains, curiosity and shards.

A source-backed local indexing layer; does not train new LLMs, invent facts,
self-deploy, or contact remote services. Remote federation requires separate
authentication and an explicit owner action.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import log
from typing import Iterable
from .cognitive_evolution import BRAINS, terms

MAX_ITEMS = 50000
MAX_SUBBRAINS = 128
MAX_DEPTH = 4
MAX_SHARDS = 32

@dataclass(frozen=True)
class Evidence:
    id: str
    brain: str
    text: str
    source: str
    scope: str = "global"
    confirmed: bool = True

    def valid(self) -> bool:
        return (bool(self.id and self.source and self.confirmed)
                and self.brain in BRAINS and 0 < len(self.text) <= 4000)

@dataclass(frozen=True)
class Subbrain:
    id: str
    parent: str
    topic: str
    evidence_ids: tuple[str, ...]
    depth: int = 1

class InfinityGrowth:
    def __init__(self, memories: Iterable[Evidence]):
        valid = (e for e in memories if e.valid())
        self.memories = {e.id:e for e in sorted(valid,key=lambda e:e.id)[:MAX_ITEMS]}
        self.subbrains: dict[str,Subbrain] = {}
        self._assignments: dict[str,set[str]] = defaultdict(set)

    def grow(self, *, minimum_sources: int=3, max_new: int=32) -> list[Subbrain]:
        """Create only reproducible, independent-source lexical specializations."""
        groups: dict[tuple[str,str,str],set[str]] = defaultdict(set)
        sources: dict[tuple[str,str,str],set[str]] = defaultdict(set)
        for e in self.memories.values():
            for topic in sorted(terms(e.text))[:80]:
                if len(topic)<4: continue
                key=(e.brain,e.scope,topic)
                groups[key].add(e.id)
                sources[key].add(e.source)
        created=[]
        for (brain,scope,topic),ids in sorted(groups.items(),
                  key=lambda pair:(-len(sources[pair[0]]),pair[0])):
            if len(created)>=min(max_new,MAX_SUBBRAINS) or len(self.subbrains)>=MAX_SUBBRAINS:
                break
            if len(sources[(brain,scope,topic)])<max(2,minimum_sources):
                continue
            key=sha256(f"{brain}|{scope}|{topic}".encode()).hexdigest()[:16]
            if key in self.subbrains: continue
            node=Subbrain(key,brain,topic,tuple(sorted(ids)))
            self.subbrains[key]=node
            self._assignments[brain].add(key)
            created.append(node)
        return created

    def specialize(self, parent: str, *, minimum_sources: int=3) -> list[Subbrain]:
        """One bounded recursive level; no child fabricated from a single fact."""
        root=self.subbrains.get(parent)
        if not root or root.depth>=MAX_DEPTH: return []
        evidence=[self.memories[i] for i in root.evidence_ids if i in self.memories]
        topics=Counter(t for e in evidence for t in terms(e.text) if t!=root.topic and len(t)>=4)
        new=[]
        for topic,_ in topics.most_common(8):
            selected=[e for e in evidence if topic in terms(e.text)]
            if len({e.source for e in selected})<max(2,minimum_sources):continue
            key=sha256(f"{parent}|{topic}".encode()).hexdigest()[:16]
            if key in self.subbrains: continue
            if len(self.subbrains)>=MAX_SUBBRAINS: break
            node=Subbrain(key,parent,topic,tuple(sorted(e.id for e in selected)),root.depth+1)
            self.subbrains[key]=node
            new.append(node)
        return new

    def questions(self, *, max_questions: int=12) -> list[dict]:
        """Detect evidence gaps, not alleged truths; never browse automatically."""
        groups:dict[tuple[str,str],set[str]]=defaultdict(set)
        for e in self.memories.values():
            for topic in terms(e.text):
                if len(topic)>=4: groups[(e.brain,topic)].add(e.source)
        gaps=sorted(((brain,topic,len(src)) for (brain,topic),src in groups.items()
                     if len(src)<3),key=lambda t:(t[2],t[0],t[1]))
        return [{"brain":brain,"topic":topic,"sources":n,
                 "question":f"Какие независимые источники подтверждают тему «{topic}»?"}
                for brain,topic,n in gaps[:max(0,min(max_questions,50))]]

    @staticmethod
    def shard_id(key: str, count: int) -> int:
        if not 1<=count<=MAX_SHARDS: raise ValueError("Invalid shard count")
        return int.from_bytes(sha256(key.encode()).digest()[:8],"big")%count

    def distribute(self, count: int=8) -> dict[int,tuple[str,...]]:
        """Stable deterministic local partition map; no data leaves this process."""
        result:dict[int,list[str]]={i:[] for i in range(count)}
        for id_,e in self.memories.items():
            result[self.shard_id(f"{e.scope}:{id_}",count)].append(id_)
        return {k:tuple(sorted(v)) for k,v in result.items()}

    def metrics(self) -> dict:
        return {"memories":len(self.memories),"subbrains":len(self.subbrains),
                "maxSubbrains":MAX_SUBBRAINS,"maxDepth":MAX_DEPTH,
                "remoteExecution":False,"automaticExternalResearch":False}
