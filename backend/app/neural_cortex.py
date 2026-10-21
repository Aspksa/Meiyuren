"""Neural Cortex 2.0: source-preserving, bounded associative graph.

No new user facts are inferred. Similarity is lexical/topic-based; it is not
causal reasoning or embedding-based semantic understanding.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from math import log
from typing import Iterable
from .cognitive_evolution import terms, BRAINS

MAX_NODES = 600
MAX_EDGES = 1200
MAX_DEGREE = 12

@dataclass(frozen=True)
class Node:
    id: str
    brain: str
    text: str
    source: str
    confirmed: bool = True
    scope: str = "global"

    def valid(self) -> bool:
        return bool(self.id and self.source and self.confirmed and
                    self.brain in BRAINS and len(self.text) <= 4000)


class NeuralCortex:
    """Ephemeral associative index. Does not bypass Memory Core visibility."""

    def __init__(self, nodes: Iterable[Node]):
        accepted = [n for n in nodes if n.valid()]
        self.nodes = {n.id: n for n in sorted(accepted, key=lambda n: n.id)[:MAX_NODES]}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)
        self.feedback: dict[tuple[str, str], float] = {}
        self._build()

    def _build(self) -> None:
        token_sets = {id_: terms(node.text) for id_, node in self.nodes.items()}
        frequency = Counter(t for ts in token_sets.values() for t in ts)
        proposals = []
        keys = sorted(self.nodes)
        for i, left in enumerate(keys):
            a = self.nodes[left]
            for right in keys[i + 1:]:
                b = self.nodes[right]
                if a.brain == b.brain or not (a.scope == b.scope or
                        a.scope == "global" or b.scope == "global"):
                    continue
                common = token_sets[left] & token_sets[right]
                if len(common) < 2:
                    continue
                informative = sum(1 / (1 + log(1 + frequency[t])) for t in common)
                union = token_sets[left] | token_sets[right]
                value = informative / max(1, len(union))
                if value >= 0.08:
                    proposals.append((-value, left, right))
        for neg, left, right in sorted(proposals):
            if sum(len(v) for v in self.edges.values()) // 2 >= MAX_EDGES:
                break
            if len(self.edges[left]) >= MAX_DEGREE or len(self.edges[right]) >= MAX_DEGREE:
                continue
            self.edges[left][right] = -neg
            self.edges[right][left] = -neg

    def adjust(self, left: str, right: str, helpful: bool) -> bool:
        if right not in self.edges.get(left, {}):
            return False
        pair = tuple(sorted((left, right)))
        previous = self.feedback.get(pair, 0.0)
        self.feedback[pair] = max(-0.3, min(0.3, previous + (0.05 if helpful else -0.05)))
        return True

    def recall(self, seed: str, scope: str, *, depth: int = 3,
               limit: int = 12, budget: int = 80) -> list[dict]:
        if seed not in self.nodes or depth < 1 or limit < 1:
            return []
        if self.nodes[seed].scope not in ("global", scope):
            return []
        queue = deque([(seed, 0, 1.0)])
        visited = {seed}
        results = []
        expanded = 0
        while queue and len(results) < min(limit, 32) and expanded < min(budget, 200):
            source, hop, strength = queue.popleft()
            if hop >= min(depth, 4):
                continue
            for target, raw in sorted(self.edges.get(source, {}).items(),
                                      key=lambda v: -v[1]):
                expanded += 1
                if expanded > min(budget, 200):
                    break
                if target in visited or self.nodes[target].scope not in ("global", scope):
                    continue
                visited.add(target)
                adjustment = self.feedback.get(tuple(sorted((source, target))), 0)
                score = strength * max(0.0, min(1.0, raw + adjustment)) * (0.85 ** hop)
                if score <= 0:
                    continue
                results.append({"id": target, "brain": self.nodes[target].brain,
                                "source": self.nodes[target].source,
                                "score": round(score, 5), "hops": hop + 1})
                queue.append((target, hop + 1, score))
                if len(results) >= min(limit, 32):
                    break
        return results

    def prune(self, minimum: float = 0.08) -> int:
        removed = 0
        for left in list(self.edges):
            for right, raw in list(self.edges[left].items()):
                if left >= right:
                    continue
                pair = (left, right)
                if raw + self.feedback.get(pair, 0) < minimum:
                    self.edges[left].pop(right, None)
                    self.edges[right].pop(left, None)
                    self.feedback.pop(pair, None)
                    removed += 1
        return removed

    def diagnostics(self) -> dict:
        return {"nodes": len(self.nodes), "edges": sum(map(len, self.edges.values())) // 2,
                "maxDepth": 4, "maxEdges": MAX_EDGES,
                "meaning": "lexical associative evidence, not verified causality"}
