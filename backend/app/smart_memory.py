"""Deterministic, privacy-first extraction of durable user statements from natural chat.

No LLM, remote calls, inferred identities or assistant-generated facts.
This is intentionally high precision: silence is preferable to invented memory.
"""
from __future__ import annotations
import re

# Require explicit first-person ownership of a durable fact, even without "Запомни".
STATEMENT = re.compile(
    r"(?iu)^\s*(?:"
    r"(?:мой|моя|моё|мои|наша|наш)\s+(?:проект|цель|задача|хобби|привычка|"
    r"репозиторий|план|решение|предпочтение)\b"
    r"|я\s+(?:работаю\s+над|разрабатываю|создаю|изучаю|учу|"
    r"планирую|хочу|решил|решила|выбрал|выбрала|предпочитаю|"
    r"обычно|регулярно|каждый\s+день|умею|освоил|освоила)\b"
    r"|мы\s+(?:разрабатываем|создаём|решили|выбрали)\b"
    r"|мне\s+(?:нравится|нравятся)\b"
    r"|меня\s+зовут\b"
    r"|(?:мой|моя|моё|мои)\s+любим\w*\b"
    r"|я\s+работаю\s+(?:в|на|кем|программист\w*|разработчик\w*|дизайнер\w*|"
    r"инженер\w*|учител\w*|аналитик\w*|менеджер\w*)\b"
    r")"
)
# Reject quoted or hypothetical material; no third-party statements or instructions.
UNTRUSTED = re.compile(
    r"(?iu)(?:\b(?:если|допустим|представь|предположим|возможно|"
    r"наверное|кажется|говорят|по\s+слухам)\b|"
    r"https?://|\b(?:пароль|токен|api.key|секрет|паспорт|"
    r"адрес|телефон|диагноз|болею|религия|политические\s+взгляды)\b)"
)

def durable_statement(text: str) -> str | None:
    value=text.strip()
    if not 8<=len(value)<=400 or "\n" in value or "?" in value:
        return None
    if value.startswith((">", '"', "«", "`", "-", "*")):
        return None
    if not STATEMENT.match(value) or UNTRUSTED.search(value):
        return None
    return value.rstrip(".! ")

def eligible_experience(text: str) -> bool:
    """Store only explicit user-owned completed learning, never model self-grading."""
    return bool(re.match(
        r"(?iu)^\s*я\s+(?:научился|научилась|освоил|освоила)\b",text))
