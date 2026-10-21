"""Саморазвитие мини-мозгов (v0.31): любопытство, новые мозги, карта роста.

Всё локально и детерминированно, без Cloud.ru и без отдельных программ:
- в режиме простоя ветки пересобираются (по словам и по смыслу), бесконечный рост
  (InfinityGrowth) ищет темы, которые выросли сразу в нескольких мозгах;
- такая тема становится предложением «нового мозга» — создаётся только после «да»;
- мини-мозги замечают пробелы (цель без срока, проект с одним фактом) и иногда
  спрашивают о них в чате, не чаще раза в несколько часов;
- снимки размеров мозгов по дням дают карту роста за неделю.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import uuid

from . import db, understanding
from .infinity_growth import Evidence, InfinityGrowth
from .memory_engine import AUTO_PRIVATE, BRAINS, SECRET, MemoryEngine, _keywords, now

# Тема становится кандидатом в новый мозг, когда о ней столько разных фактов.
PROMOTE_MIN = 8
# И когда она встречается хотя бы в двух мозгах: иначе это обычная ветка своего мозга.
PROMOTE_BRAINS = 2
MAX_PENDING = 3
MAX_QUESTIONS = 20
# Вопрос любопытства — не чаще раза в шесть часов, чтобы не надоедать.
ASK_EVERY = 6 * 3600 * 1000
STRONG = 0.6
SLEEPING = 0.12


class BrainGrowth:
    def __init__(self, path: Path, engine: MemoryEngine):
        self.path = path
        self.engine = engine

    # -- шаг простоя ------------------------------------------------------
    def grow(self) -> dict:
        """Пересобрать ветки, найти темы для новых мозгов, записать снимок роста."""
        branches = self.engine.grow_branches()
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute(
                "SELECT id,brain,content,COALESCE(source_message_id,id) AS source FROM memory_items "
                "WHERE status='confirmed' AND (expires_at IS NULL OR expires_at>?) "
                "ORDER BY updated_at DESC LIMIT 2000", (now(),)).fetchall()
        evidence = [Evidence(r["id"], r["brain"], r["content"], r["source"]) for r in rows
                    if not SECRET.search(r["content"]) and not AUTO_PRIVATE.search(r["content"])]
        growth = InfinityGrowth(evidence)
        nodes = growth.grow(minimum_sources=2, max_new=128)
        for node in list(nodes):
            growth.specialize(node.id, minimum_sources=2)
        proposals = self._propose(nodes, growth)
        self._snapshot()
        return {"branches": branches["branches"], "microbrains": branches["microbrains"],
                "subbrains": len(growth.subbrains), "proposals": proposals}

    def _propose(self, nodes, growth: InfinityGrowth) -> int:
        topics: dict[str, dict[str, set[str]]] = {}
        for node in nodes:
            # Мозг называется предметом («кофе», «Kitsune»), а не глаголом; формы слова сливаются.
            if not (node.topic.isascii() or understanding.is_noun(node.topic)):
                continue
            keys = _keywords(node.topic)
            if len(keys) != 1:
                continue
            topics.setdefault(keys.pop(), {}).setdefault(node.parent, set()).update(node.evidence_ids)
        stamp = now()
        created = 0
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                taken = {r[0] for r in conn.execute(
                    "SELECT term FROM memory_custom_brains UNION SELECT term FROM memory_brain_proposals")}
                # Устаревшие предложения (факты забыты) убираем, отказы помним.
                for row in conn.execute("SELECT id,term FROM memory_brain_proposals "
                                        "WHERE status='pending'").fetchall():
                    found = topics.get(row["term"], {})
                    if len(set().union(*found.values()) if found else set()) < PROMOTE_MIN:
                        conn.execute("DELETE FROM memory_brain_proposals WHERE id=?", (row["id"],))
                        taken.discard(row["term"])
                pending = conn.execute("SELECT COUNT(*) FROM memory_brain_proposals "
                                       "WHERE status='pending'").fetchone()[0]
                ranked = sorted(topics.items(), key=lambda t: (-len(set().union(*t[1].values())), t[0]))
                for topic, by_brain in ranked:
                    if pending + created >= MAX_PENDING:
                        break
                    facts = set().union(*by_brain.values())
                    if topic in taken or len(facts) < PROMOTE_MIN or len(by_brain) < PROMOTE_BRAINS:
                        continue
                    title = self._title(topic, [growth.memories[i].text for i in facts
                                                if i in growth.memories])
                    conn.execute("INSERT INTO memory_brain_proposals VALUES(?,?,?,?,?,'pending',?,NULL)",
                                 (str(uuid.uuid4()), topic, title, len(facts),
                                  ",".join(sorted(by_brain)), stamp))
                    created += 1
        return created

    @staticmethod
    def _title(topic: str, texts: list[str]) -> str:
        for text in texts:
            for word in text.split():
                clean = word.strip(".,!?;:«»\"'()")
                if _keywords(clean) == {topic}:
                    name = understanding.lemma(clean.casefold()) if not clean.isascii() else clean
                    name = name or clean
                    return name[:1].upper() + name[1:]
        return topic[:1].upper() + topic[1:]

    def _snapshot(self) -> None:
        today = date.today().isoformat()
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("INSERT OR REPLACE INTO memory_brain_history "
                             "SELECT ?,id,support FROM memory_branches WHERE depth<=1", (today,))
                conn.execute("DELETE FROM memory_brain_history WHERE day<?",
                             ((date.today() - timedelta(days=60)).isoformat(),))

    # -- новые мозги -------------------------------------------------------
    def proposals(self) -> list[dict]:
        with closing(db.connection(self.path)) as conn:
            rows = conn.execute("SELECT * FROM memory_brain_proposals WHERE status='pending' "
                                "ORDER BY support DESC").fetchall()
        return [dict(id=r["id"], title=r["title"], term=r["term"], support=r["support"],
                     brains=[b for b in r["brains"].split(",") if b in BRAINS]) for r in rows]

    def decide(self, proposal_id: str, accept: bool) -> dict | None:
        with closing(db.connection(self.path)) as conn:
            with conn:
                row = conn.execute("SELECT * FROM memory_brain_proposals WHERE id=? AND status='pending'",
                                   (proposal_id,)).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE memory_brain_proposals SET status=?,decided_at=? WHERE id=?",
                             ("accepted" if accept else "declined", now(), proposal_id))
                if accept:
                    conn.execute("INSERT OR IGNORE INTO memory_custom_brains VALUES(?,?,?,?)",
                                 ("custom:" + str(uuid.uuid4()), row["term"], row["title"], now()))
        if accept:
            self.engine.grow_branches()
        return {"accepted": accept, "title": row["title"]}

    def remove_brain(self, brain_id: str) -> bool:
        """Убрать свой мозг. Факты остаются в восьми основных мозгах."""
        with closing(db.connection(self.path)) as conn:
            with conn:
                row = conn.execute("SELECT term FROM memory_custom_brains WHERE id=?", (brain_id,)).fetchone()
                if not row:
                    return False
                conn.execute("DELETE FROM memory_custom_brains WHERE id=?", (brain_id,))
                # Снова не предлагать то, от чего отказались.
                conn.execute("UPDATE memory_brain_proposals SET status='declined',decided_at=? WHERE term=?",
                             (now(), row["term"]))
        self.engine.grow_branches()
        return True

    # -- любопытство ------------------------------------------------------
    def scan_questions(self) -> dict:
        """Найти пробелы: цель без срока, проект, о котором известен один факт."""
        stamp = now()
        found: list[tuple[str, str, str]] = []
        with closing(db.connection(self.path)) as conn:
            goals = conn.execute(
                "SELECT id,content FROM memory_items WHERE status='confirmed' AND brain='goals' "
                "AND due_date IS NULL AND conversation_id='global' "
                "AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC LIMIT 20",
                (stamp,)).fetchall()
            for row in goals:
                if SECRET.search(row["content"]) or AUTO_PRIVATE.search(row["content"]):
                    continue
                text = row["content"].rstrip(".!")
                found.append(("due", row["id"], f"Ты говорил: «{text}». К какому сроку хочешь это сделать?"))
        # Противоречия и прошедшие сроки из логического мозга — тоже повод уточнить.
        from .reasoning import Reasoner
        found += Reasoner(self.path, self.engine).questions()
        for entity in self.engine.entity_list():
            if entity["kind"] == "project" and entity["facts"] == 1:
                found.append(("entity", entity["id"], f"Как продвигается проект {entity['name']}?"))
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                live = {(kind, ref) for kind, ref, _ in found}
                for row in conn.execute("SELECT id,kind,ref FROM memory_curiosity WHERE status='new'"):
                    if (row["kind"], row["ref"]) not in live:  # пробел закрыт: срок появился, фактов стало больше
                        conn.execute("DELETE FROM memory_curiosity WHERE id=?", (row["id"],))
                for kind, ref, question in found[:MAX_QUESTIONS]:
                    conn.execute("INSERT OR IGNORE INTO memory_curiosity(id,kind,ref,question,created_at) "
                                 "VALUES(?,?,?,?,?)", (str(uuid.uuid4()), kind, ref, question, stamp))
                total = conn.execute("SELECT COUNT(*) FROM memory_curiosity WHERE status='new'").fetchone()[0]
        return {"questions": total}

    def next_question(self, user_text: str) -> dict | None:
        """Один вопрос к ответу чата, если давно не спрашивали и пользователь сам не спрашивает."""
        if user_text.rstrip().endswith("?") or not self.engine.policy()["curiosity"]:
            return None
        stamp = now()
        with closing(db.connection(self.path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                last = conn.execute("SELECT MAX(asked_at) FROM memory_curiosity").fetchone()[0]
                if last and stamp - last < ASK_EVERY:
                    return None
                row = conn.execute("SELECT id,question FROM memory_curiosity WHERE status='new' "
                                   "ORDER BY created_at,id LIMIT 1").fetchone()
                if not row:
                    return None
                conn.execute("UPDATE memory_curiosity SET status='asked',asked_at=? WHERE id=?",
                             (stamp, row["id"]))
        return {"id": row["id"], "question": row["question"]}

    def dismiss(self, question_id: str) -> bool:
        with closing(db.connection(self.path)) as conn:
            with conn:
                return conn.execute("UPDATE memory_curiosity SET status='dismissed' WHERE id=?",
                                    (question_id,)).rowcount > 0

    # -- карта ------------------------------------------------------------
    def map(self) -> dict:
        week = (date.today() - timedelta(days=7)).isoformat()
        tree = self.engine.branch_tree()
        names = {b["id"]: b["title"] for b in tree["custom"]}
        with closing(db.connection(self.path)) as conn:
            past = {r["node"]: r["support"] for r in conn.execute(
                "SELECT h.node,h.support FROM memory_brain_history h JOIN ("
                "SELECT node,MIN(day) AS day FROM memory_brain_history WHERE day>=? GROUP BY node"
                ") f ON f.node=h.node AND f.day=h.day", (week,))}
            strength = {r["branch_id"]: (r["avg"], r["latest"]) for r in conn.execute(
                "SELECT bm.branch_id,AVG(COALESCE(s.strength,0.45)) AS avg,MAX(m.updated_at) AS latest "
                "FROM memory_branch_members bm JOIN memory_items m ON m.id=bm.memory_id "
                "LEFT JOIN memory_strength s ON s.memory_id=m.id GROUP BY bm.branch_id")}
        roots = []
        for root in list(BRAINS) + list(names):
            nodes = [b for b in tree["branches"] if b["brain"] == root and b["depth"] > 0]
            top = [b for b in tree["branches"] if b["id"] == root]
            support = top[0]["support"] if top else 0
            scored = [dict(id=b["id"], title=b["title"], support=b["support"], depth=b["depth"],
                           strength=round(strength.get(b["id"], (0.45, 0))[0], 2))
                      for b in nodes if b["depth"] == 1]
            roots.append({
                "id": root, "title": names.get(root), "custom": root in names,
                "facts": support, "growth": support - past.get(root, support),
                "branches": len(nodes),
                "newBranches": sum(1 for b in nodes if b["depth"] == 1 and b["id"] not in past),
                "strong": sorted((b for b in scored if b["strength"] >= STRONG),
                                 key=lambda b: -b["support"])[:4],
                "sleeping": sorted((b for b in scored if b["strength"] < SLEEPING),
                                   key=lambda b: b["strength"])[:4],
            })
        return {"roots": roots, "proposals": self.proposals()}
