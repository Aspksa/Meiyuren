"""Логический мозг (v0.32): выводы из подтверждённых фактов, по правилам, локально.

Выводы — не факты пользователя. Они хранятся отдельно (memory_inferences), всегда
помечены как «вывод», ссылаются на свои основания и исчезают вместе с ними.
Пользователь может отклонить вывод (👎) — тогда он больше не появится.

Правила:
1. цепочки: «мой брат Петя…» + «мой брат живёт в Казани» → это про Петю;
2. время: срок сегодня, завтра, через N дней, прошёл;
3. противоречия: «я не люблю кофе» и «я люблю кофе» — что верно сейчас?;
4. причина и следствие: привычка или проект, которые помогают цели;
5. обобщения: три и больше фактов «по субботам…» → правило «суббота — плавание, бассейн».
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from datetime import date
import hashlib
from pathlib import Path
import re
import uuid

from . import db, semantic, understanding
from .memory_engine import SECRET, TOKENS, MemoryEngine, _keywords, now

MAX_FACTS = 600
MAX_INFERENCES = 200
SOON_DAYS = 7
# Правило-обобщение появляется от трёх фактов с одним и тем же временем.
RULE_MIN = 3
# Цель и привычка связаны по смыслу, если модель смысла считает их близкими.
HELPS_MATCH = semantic.MATCH

_NEGATION = re.compile(r"(?iu)(?<![\w-])(?:не|никогда|больше\s+не)(?![\w-])")
_CORE_SKIP = frozenset(("я", "мне", "меня", "у", "не", "никогда", "больше", "уже", "очень", "совсем",
                        "и", "а", "но", "в", "на", "по", "с", "к", "о", "это", "так", "тоже"))
_TIME = re.compile(
    r"(?iu)(?<![\w-])(?:по\s+|в\s+|во\s+)?(понедельник\w*|вторник\w*|сред[аеуы]\w*|четверг\w*|пятниц\w*|"
    r"суббот\w*|воскресень\w*|выходн\w*|утр\w*|вечер\w*)")
_TIME_LABEL = {
    "понедельник": "По понедельникам", "вторник": "По вторникам", "среда": "По средам",
    "четверг": "По четвергам", "пятница": "По пятницам", "суббота": "По субботам",
    "воскресенье": "По воскресеньям", "выходной": "По выходным", "выходные": "По выходным",
    "утро": "По утрам", "вечер": "По вечерам",
}
_HELP_BRAINS = {"habits": "Привычка", "projects": "Проект", "decisions": "Решение"}


def _core(text: str) -> set[str]:
    """Смысловое ядро утверждения без отрицания: «Я не люблю кофе» → {любить, кофе}."""
    words = set()
    for word in TOKENS.findall(text.casefold()):
        if word in _CORE_SKIP or len(word) < 2:
            continue
        words.add(understanding.lemma(word) or word)
    return words


def _time_key(text: str) -> str | None:
    found = _TIME.search(text)
    if not found:
        return None
    word = found.group(1).casefold()
    base = understanding.lemma(word) or word
    if base.startswith("выходн"):
        return "выходные"
    if base.startswith("утр"):
        return "утро"
    if base.startswith("вечер"):
        return "вечер"
    return base if base in _TIME_LABEL else None


def _themes(texts: list[str], skip: str) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        seen = set()
        for word in TOKENS.findall(text.casefold()):
            base = understanding.lemma(word) or word
            if (len(base) < 3 or base in seen or _time_key(word) == skip or base in _CORE_SKIP
                    or not understanding.is_noun(word)):
                continue
            seen.add(base)
            counts[base] += 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:4]


def _about(name: str) -> str:
    """«про Петю», «про Лену»: имя в винительном падеже, если словарь его знает."""
    morph = understanding._morph()
    if morph is not None and not name.isascii():
        for parse in morph.parse(name):
            if "Name" in parse.tag:
                form = parse.inflect({"accs"})
                if form:
                    return form.word.capitalize()
    return name


def _quote(text: str) -> str:
    return "«" + text.rstrip(".!") + "»"


class Reasoner:
    def __init__(self, path: Path, engine: MemoryEngine):
        self.path = path
        self.engine = engine

    # -- построение выводов -------------------------------------------------
    def rebuild(self, today: date | None = None) -> dict:
        today = today or date.today()
        with closing(db.connection(self.path)) as conn:
            facts = conn.execute(
                "SELECT id,content,brain,due_date FROM memory_items WHERE status='confirmed' "
                "AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC LIMIT ?",
                (now(), MAX_FACTS)).fetchall()
            facts = [f for f in facts if not SECRET.search(f["content"])]
            mentions = conn.execute(
                "SELECT e.id,e.kind,e.key,e.name,e.role,x.memory_id FROM memory_entities e "
                "JOIN memory_entity_mentions x ON x.entity_id=e.id").fetchall()
            vectors = self.engine._branch_vectors(conn)
        found: list[tuple[str, str, list[str], float, bool]] = []
        found += self._chains(facts, mentions)
        found += self._time(facts, today)
        found += self._conflicts(facts)
        found += self._helps(facts, vectors)
        found += self._rules(facts)
        return self._store(found[:MAX_INFERENCES])

    def _chains(self, facts, mentions):
        by_id = {f["id"]: f for f in facts}
        named: dict[str, list] = defaultdict(list)
        role_only: dict[str, list[str]] = defaultdict(list)
        for m in mentions:
            if m["kind"] != "person" or not m["role"] or m["memory_id"] not in by_id:
                continue
            if m["key"].startswith("роль:"):
                role_only[m["role"]].append(m["memory_id"])
            else:
                named[m["role"]].append(m)
        out = []
        for role, fact_ids in role_only.items():
            people = {m["key"]: m for m in named.get(role, [])}
            if len(people) != 1:
                continue  # два брата — не угадываем, о ком речь
            person = next(iter(people.values()))
            for fact_id in fact_ids:
                if fact_id == person["memory_id"]:
                    continue
                text = f"{_quote(by_id[fact_id]['content'])} — это про {_about(person['name'])} ({role})"
                out.append(("chain", text, [fact_id, person["memory_id"]], 0.8, False))
        return out

    def _time(self, facts, today):
        out = []
        for f in facts:
            if not f["due_date"]:
                continue
            try:
                days = (date.fromisoformat(f["due_date"]) - today).days
            except ValueError:
                continue
            what = _quote(f["content"])
            if days < 0:
                out.append(("overdue", f"Срок {what} прошёл {-days} дн. назад. Это уже сделано?",
                            [f["id"]], 1.0, True))
            elif days == 0:
                out.append(("time", f"Срок {what} — сегодня", [f["id"]], 1.0, False))
            elif days == 1:
                out.append(("time", f"Срок {what} — завтра", [f["id"]], 1.0, False))
            elif days <= SOON_DAYS:
                out.append(("time", f"Срок {what} — через {days} дн.", [f["id"]], 1.0, False))
        return out

    def _conflicts(self, facts):
        cores = [(f, bool(_NEGATION.search(f["content"])), _core(f["content"])) for f in facts]
        out = []
        for a, a_neg, a_core in cores:
            if not a_neg or len(a_core) < 2:
                continue
            for b, b_neg, b_core in cores:
                if b_neg or b["id"] == a["id"] or len(a_core & b_core) < 2:
                    continue
                if a_core <= b_core or b_core <= a_core:
                    text = f"Противоречие: {_quote(a['content'])} и {_quote(b['content'])}. Что верно сейчас?"
                    out.append(("conflict", text, [a["id"], b["id"]], 0.9, True))
        return out

    def _helps(self, facts, vectors):
        goals = [f for f in facts if f["brain"] == "goals"]
        others = [f for f in facts if f["brain"] in _HELP_BRAINS]
        out = []
        for goal in goals:
            g_keys = _keywords(goal["content"])
            for other in others:
                common = g_keys & _keywords(other["content"])
                close = (goal["id"] in vectors and other["id"] in vectors and semantic.similarity(
                    vectors[goal["id"]], vectors[other["id"]]) >= HELPS_MATCH)
                if not common and not close:
                    continue
                label = _HELP_BRAINS[other["brain"]]
                text = f"{label} {_quote(other['content'])} помогает цели {_quote(goal['content'])}"
                out.append(("helps", text, [other["id"], goal["id"]], 0.7 if common else 0.6, False))
        return out

    def _rules(self, facts):
        groups: dict[str, list] = defaultdict(list)
        for f in facts:
            if f["brain"] == "episodes":
                continue
            key = _time_key(f["content"])
            if key:
                groups[key].append(f)
        out = []
        for key, items in groups.items():
            if len(items) < RULE_MIN:
                continue
            themes = _themes([f["content"] for f in items], key)
            if not themes:
                continue
            text = f"Правило: {_TIME_LABEL[key].lower()} у тебя обычно {', '.join(themes)}"
            out.append(("rule", text, [f["id"] for f in items], min(1.0, len(items) / 5), False))
        return out

    def _store(self, found) -> dict:
        stamp = now()
        fresh = {}
        for kind, content, premises, confidence, ask in found:
            digest = hashlib.sha256((kind + "|" + "|".join(sorted(premises)) + "|" + content)
                                    .encode()).hexdigest()
            fresh.setdefault(digest, (kind, content, premises, confidence, ask))
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = {r["digest"]: r for r in conn.execute(
                    "SELECT id,digest,status FROM memory_inferences")}
                stale = [r["id"] for d, r in existing.items() if r["status"] == "active" and d not in fresh]
                for inference_id in stale:
                    conn.execute("DELETE FROM memory_inference_premises WHERE inference_id=?", (inference_id,))
                    conn.execute("DELETE FROM memory_inferences WHERE id=?", (inference_id,))
                added = 0
                for digest, (kind, content, premises, confidence, ask) in fresh.items():
                    if digest in existing:
                        continue  # уже есть или отклонён пользователем
                    inference_id = str(uuid.uuid4())
                    conn.execute("INSERT INTO memory_inferences VALUES(?,?,?,?,?,?,'active',?,?)",
                                 (inference_id, kind, content, digest, confidence, int(ask), stamp, stamp))
                    conn.executemany("INSERT OR IGNORE INTO memory_inference_premises VALUES(?,?)",
                                     [(inference_id, p) for p in premises])
                    added += 1
                total = conn.execute("SELECT COUNT(*) FROM memory_inferences WHERE status='active'").fetchone()[0]
        return {"inferences": total, "added": added, "removed": len(stale)}

    # -- использование ------------------------------------------------------
    def listing(self) -> list[dict]:
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute("SELECT * FROM memory_inferences WHERE status='active' "
                                "ORDER BY ask DESC,confidence DESC,created_at DESC LIMIT ?",
                                (MAX_INFERENCES,)).fetchall()
            return [self._row(conn, r) for r in rows]

    def _row(self, conn, row) -> dict:
        premises = conn.execute(
            "SELECT m.id,m.content,m.brain FROM memory_inference_premises p "
            "JOIN memory_items m ON m.id=p.memory_id WHERE p.inference_id=?", (row["id"],)).fetchall()
        return {"id": row["id"], "kind": row["kind"], "content": row["content"],
                "confidence": row["confidence"], "ask": bool(row["ask"]),
                "because": [dict(id=p["id"], content=p["content"], brain=p["brain"]) for p in premises]}

    def relevant(self, query: str, cloud_mode: bool, limit: int = 3) -> list[dict]:
        """Выводы, относящиеся к вопросу. В облако — только если все основания можно туда."""
        keys = _keywords(query)
        if not keys:
            return []
        policy = self.engine.policy()
        if cloud_mode and not policy["allow_cloud_facts"]:
            return []
        shared = self.engine.cloud_brains_allowed() if cloud_mode else set()
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute("SELECT * FROM memory_inferences WHERE status='active'").fetchall()
            scored = []
            for row in rows:
                overlap = len(keys & _keywords(row["content"]))
                if overlap:
                    scored.append((overlap + row["confidence"], row))
            scored.sort(key=lambda x: -x[0])
            out = []
            for _, row in scored:
                premises = conn.execute(
                    "SELECT m.* FROM memory_inference_premises p JOIN memory_items m ON m.id=p.memory_id "
                    "WHERE p.inference_id=? AND m.status='confirmed'", (row["id"],)).fetchall()
                if not premises or (cloud_mode and not all(self.engine._cloud_ok(p, shared) for p in premises)):
                    continue
                out.append(self._row(conn, row))
                if len(out) >= limit:
                    break
        return out

    def reject(self, inference_id: str) -> bool:
        with closing(db.connection(self.path)) as conn:
            with conn:
                changed = conn.execute("UPDATE memory_inferences SET status='rejected',updated_at=? "
                                       "WHERE id=? AND status='active'", (now(), inference_id)).rowcount
                conn.execute("DELETE FROM memory_curiosity WHERE kind='logic' AND ref=?", (inference_id,))
        return changed > 0

    def questions(self) -> list[tuple[str, str, str]]:
        """Выводы, о которых стоит спросить: противоречия и прошедшие сроки."""
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute("SELECT id,content FROM memory_inferences WHERE status='active' AND ask=1 "
                                "ORDER BY created_at LIMIT 10").fetchall()
        return [("logic", r["id"], r["content"]) for r in rows]

