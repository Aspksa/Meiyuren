"""Neural Cortex 3.0: source-preserving, bounded associative graph.

No new user facts are inferred. An edge joins two facts from different brains
when they share at least two informative words, or when the local meaning
model (semantic.py) finds them close. Edges are associative evidence, not
causal reasoning.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
from math import log
from typing import Iterable, Mapping, Sequence
from .cognitive_evolution import terms, BRAINS

try:  # numpy приходит вместе с fastembed; без него смысл считается только для лексических пар.
    import numpy
except ImportError:  # pragma: no cover - зависит от окружения
    numpy = None


def stems(text: str) -> set[str]:
    """Same Russian stemming as Memory Core, so «проект» and «проекта» connect."""
    from .memory_engine import search_stem
    return {search_stem(t) for t in terms(text)}

MAX_NODES = 1500
MAX_EDGES = 3000
MAX_DEGREE = 12
LEXICAL_MIN = 0.08
# Строже, чем порог поиска semantic.MATCH: ребро без общих слов должно быть заметно ближе.
SEMANTIC_MIN = 0.6
# Слова, встречающиеся в большой доле фактов, не создают рёбер: иначе получаются клики.
COMMON_SHARE = 0.25

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
    """Associative index. Does not bypass Memory Core visibility."""

    def __init__(self, nodes: Iterable[Node],
                 vectors: Mapping[str, Sequence[float]] | None = None):
        # Порядок вызывающего сохраняется при обрезке: Memory Core передаёт свежие факты первыми.
        kept: dict[str, Node] = {}
        for node in nodes:
            if node.valid() and node.id not in kept:
                kept[node.id] = node
                if len(kept) >= MAX_NODES:
                    break
        self.nodes = {id_: kept[id_] for id_ in sorted(kept)}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)
        self.evidence: dict[tuple[str, str], dict] = {}
        self.feedback: dict[tuple[str, str], float] = {}
        self._build(vectors or {})

    def _linkable(self, a: Node, b: Node) -> bool:
        return a.brain != b.brain and (a.scope == b.scope or
                                       a.scope == "global" or b.scope == "global")

    def _meaning(self, vectors: Mapping[str, Sequence[float]],
                 lexical: dict[tuple[str, str], tuple]) -> dict[tuple[str, str], float]:
        ids = [i for i in self.nodes if i in vectors]
        if len(ids) < 2:
            return {}
        result: dict[tuple[str, str], float] = {}
        if numpy is None:
            for pair in lexical:
                if pair[0] in vectors and pair[1] in vectors:
                    result[pair] = sum(x * y for x, y in zip(vectors[pair[0]], vectors[pair[1]]))
            return result
        matrix = numpy.asarray([vectors[i] for i in ids], dtype=numpy.float32)
        scores = matrix @ matrix.T
        rows, cols = numpy.nonzero(numpy.triu(scores >= SEMANTIC_MIN, k=1))
        for r, c in zip(rows.tolist(), cols.tolist()):
            result[(ids[r], ids[c])] = float(scores[r, c])
        for left, right in lexical:
            if (left, right) not in result and left in vectors and right in vectors:
                result[(left, right)] = float(numpy.dot(vectors[left], vectors[right]))
        return result

    def _build(self, vectors: Mapping[str, Sequence[float]]) -> None:
        token_sets = {id_: stems(node.text) for id_, node in self.nodes.items()}
        frequency = Counter(t for ts in token_sets.values() for t in ts)
        postings: dict[str, list[str]] = defaultdict(list)
        common_limit = max(24, int(len(self.nodes) * COMMON_SHARE))
        for id_ in self.nodes:
            for token in token_sets[id_]:
                postings[token].append(id_)
        shared: dict[tuple[str, str], list[str]] = defaultdict(list)
        for token, ids in postings.items():
            if len(ids) < 2 or len(ids) > common_limit:
                continue
            for i, left in enumerate(ids):
                for right in ids[i + 1:]:
                    shared[(left, right)].append(token)
        lexical: dict[tuple[str, str], tuple] = {}
        for (left, right), common in shared.items():
            if len(common) < 2 or not self._linkable(self.nodes[left], self.nodes[right]):
                continue
            informative = sum(1 / (1 + log(1 + frequency[t])) for t in common)
            # Нормировка по меньшему факту: длинные факты тоже связываются.
            smaller = min(len(token_sets[left]), len(token_sets[right]))
            value = informative / max(1, smaller)
            if value >= LEXICAL_MIN:
                lexical[(left, right)] = (value, sorted(common))
        meaning = self._meaning(vectors, lexical)
        proposals = []
        for pair in set(lexical) | {p for p, v in meaning.items() if v >= SEMANTIC_MIN}:
            left, right = pair
            if not self._linkable(self.nodes[left], self.nodes[right]):
                continue
            lex, common = lexical.get(pair, (0.0, []))
            close = meaning.get(pair)
            if close is not None and close >= SEMANTIC_MIN:
                kind = "both" if lex else "semantic"
                weight = 0.6 * close + 0.4 * lex
            else:
                kind, weight = "lexical", lex
            proposals.append((-round(weight, 6), left, right, kind, common, close))
        count = 0
        for neg, left, right, kind, common, close in sorted(proposals):
            if count >= MAX_EDGES:
                break
            if len(self.edges[left]) >= MAX_DEGREE or len(self.edges[right]) >= MAX_DEGREE:
                continue
            self.edges[left][right] = -neg
            self.edges[right][left] = -neg
            self.evidence[(left, right)] = {
                "kind": kind, "terms": common[:6],
                "meaning": round(close, 3) if close is not None else None,
            }
            count += 1

    def adjust(self, left: str, right: str, helpful: bool) -> bool:
        if right not in self.edges.get(left, {}):
            return False
        pair = tuple(sorted((left, right)))
        previous = self.feedback.get(pair, 0.0)
        self.feedback[pair] = max(-0.3, min(0.3, previous + (0.05 if helpful else -0.05)))
        return True

    def weight(self, left: str, right: str) -> float:
        raw = self.edges.get(left, {}).get(right)
        if raw is None:
            return 0.0
        return max(0.0, min(1.0, raw + self.feedback.get(tuple(sorted((left, right))), 0.0)))

    def recall(self, seed: str, scope: str, *, depth: int = 3,
               limit: int = 12, budget: int = 80,
               allowed: set[str] | None = None) -> list[dict]:
        """Best-first walk: each fact is reached by its strongest path, never through hidden ones."""
        if seed not in self.nodes or depth < 1 or limit < 1:
            return []
        if self.nodes[seed].scope not in ("global", scope):
            return []
        if allowed is not None and seed not in allowed:
            return []
        cap, spend, max_depth = min(limit, 32), min(budget, 200), min(depth, 4)
        heap = [(-1.0, 0, seed, "")]
        best = {seed: 1.0}
        done: set[str] = set()
        results = []
        expanded = 0
        while heap and len(results) < cap and expanded < spend:
            neg, hop, source, via = heapq.heappop(heap)
            if source in done:
                continue
            done.add(source)
            if source != seed:
                pair = tuple(sorted((via, source)))
                results.append({"id": source, "brain": self.nodes[source].brain,
                                "source": self.nodes[source].source,
                                "score": round(-neg, 5), "hops": hop, "via": via,
                                "kind": self.evidence.get(pair, {}).get("kind", "lexical")})
            if hop >= max_depth:
                continue
            for target in self.edges.get(source, {}):
                expanded += 1
                if expanded > spend:
                    break
                if target in done or self.nodes[target].scope not in ("global", scope):
                    continue
                if allowed is not None and target not in allowed:
                    continue
                score = -neg * self.weight(source, target) * (0.85 ** hop)
                if score <= 0 or score <= best.get(target, 0.0):
                    continue
                best[target] = score
                heapq.heappush(heap, (-score, hop + 1, target, source))
        return results

    def prune(self, minimum: float = LEXICAL_MIN) -> int:
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
                    self.evidence.pop(pair, None)
                    removed += 1
        return removed

    def edge_list(self, allowed: set[str] | None = None, limit: int = MAX_EDGES) -> list[dict]:
        """Рёбра для визуализации: без текста фактов, только ID, вид связи и вес."""
        result = []
        for (left, right), info in self.evidence.items():
            if right not in self.edges.get(left, {}):
                continue
            if allowed is not None and (left not in allowed or right not in allowed):
                continue
            result.append({"source": left, "target": right, "kind": info["kind"],
                           "weight": round(self.weight(left, right), 4),
                           "adjustment": round(self.feedback.get((left, right), 0.0), 4)})
        result.sort(key=lambda e: (-e["weight"], e["source"], e["target"]))
        return result[:limit]

    def diagnostics(self) -> dict:
        kinds = Counter(info["kind"] for info in self.evidence.values())
        return {"nodes": len(self.nodes), "edges": sum(map(len, self.edges.values())) // 2,
                "lexicalEdges": kinds["lexical"], "semanticEdges": kinds["semantic"],
                "bothEdges": kinds["both"], "learnedSynapses": sum(1 for v in self.feedback.values() if v),
                "maxDepth": 4, "maxEdges": MAX_EDGES, "maxNodes": MAX_NODES,
                "meaning": "associative evidence (shared words or local meaning model), not verified causality"}
