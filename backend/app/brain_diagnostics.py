"""Verified, deterministic brain telemetry for both chat transports.

Never ask an LLM to invent runtime architecture or counts.
"""
from __future__ import annotations
import re
from .cognitive_evolution import BRAINS

_DIAG = re.compile(r"(?:диагностик|провер(?:ь|ка|ить)|статус|состояни|самодиагностик).{0,90}(?:8\s*мозг|восьми\s*мозг|мозг|памят)|(?:8\s*мозг|восемь\s*мозг).{0,90}(?:диагностик|статус|провер)",re.I|re.S)

def is_diagnostic_request(text: str) -> bool:
    return bool(_DIAG.search(text[:2000]))

def diagnostic_report(status: dict) -> str:
    network=status.get("network") or {}
    counts=network.get("brains") or {}
    lines=["Диагностика Meiyuren (фактические счётчики локального backend):"]
    for name in BRAINS:
        n=counts.get(name,0)
        lines.append(f"• {name}: подтверждённых записей {n}")
    lines.extend([
        f"Связи памяти: {network.get('links',0)}",
        f"Нейронные векторы: {network.get('neuralVectors',0)}",
        f"Тематические ветви: {status.get('autonomousBranches',0)}",
        f"Ожидающие подтверждения: {status.get('pending',0)}",
        f"Очередь задач: {status.get('jobs',0)}",
        f"Система Cortex: {status.get('cortex',{}).get('edges',0)} связей между узлами",
        f"Эволюционные оценки: {status.get('evolution',{}).get('evaluations',0)}",
    ])
    if not status.get("facts",0):
        lines.append("В памяти пока нет подтверждённых фактов. "
                     "Это не отсутствие восьми логических модулей: нечему образовывать связи. "
                     "Для автоматического извлечения нужны прямые утверждения пользователя "
                     "вроде «Запомни: мой проект — Meiyuren»; обычные вопросы не сохраняются как факты.")
    lines.append("Это системные метрики, а не доказательство восьми независимых LLM.")
    return "\n".join(lines)
