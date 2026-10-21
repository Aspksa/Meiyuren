"""Понимание 2.0, слой 1: разбор сообщения на правилах, без моделей и сети.

Делит сообщение на утверждения, приводит слова к начальной форме (pymorphy3,
если установлен), понимает относительные даты, перемены («бросил», «больше не»)
и местоимения «он/она» в пределах сообщения и предыдущей реплики.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import re

try:  # Лемматизатор необязателен: без него работает обрезка окончаний.
    import pymorphy3
except ImportError:  # pragma: no cover - проверяется окружением
    pymorphy3 = None

_SENTENCE = re.compile(r"(?<=[.!?;…])\s+|\n+")
# Реплики, которые не несут факта: приветствия, вежливость, встречные вопросы.
_FILLER = re.compile(
    r"(?iu)^\s*(?:привет\w*|здравствуй\w*|добр\w+\s+(?:утро|день|вечер)|хай|"
    r"спасибо|благодарю|пока|ок|окей|ага|угу|да|нет|ну|кстати|слушай|смотри|"
    r"мэйюрэн|а\s+ты|а\s+у\s+тебя)\s*[,.!…]*\s*"
)
# Слова времени в начале фразы не мешают узнать утверждение: «Сегодня начал учить Rust».
_LEAD_TIME = re.compile(
    r"(?iu)^\s*(?:сегодня|вчера|позавчера|теперь|сейчас|уже|наконец|недавно|"
    r"с\s+утра|на\s+днях|в\s+этом\s+году|с\s+понедельника)\s*,?\s+"
)

_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
    "пятниц": 4, "суббот": 5, "воскресень": 6,
}
_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_MONTH_WORD = r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]|июн\w*|июл\w*|август\w*|" \
              r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
_DATE_PATTERNS = (
    ("relative_day", re.compile(r"(?iu)\b(послезавтра|завтра|сегодня)\b")),
    ("weekday", re.compile(r"(?iu)\b(?:в|во|к|до|на)\s+(?:эт\w+\s+|следующ\w+\s+)?"
                           r"(понедельник|вторник|сред[уеы]|четверг|пятниц[уеы]|суббот[уеы]|воскресень[ея])\b")),
    ("in_units", re.compile(r"(?iu)\bчерез\s+(\d+|одну|один|две|два|три|пару)?\s*"
                            r"(д(?:ень|ня|ней)|недел[июь]|месяц\w*|год\w*|лет)\b")),
    ("day_month", re.compile(r"(?iu)\b(?:к|до|на|в)?\s*(\d{1,2})\s+" + _MONTH_WORD + r"\b")),
    # Только «к 25.12» / «до 01.11.2026»: «Python 3.11» датой не считается.
    ("numeric", re.compile(r"(?iu)\b(?:к|до|на)\s+(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b")),
    ("month", re.compile(r"(?iu)\b(?:к|до|в|на)\s+" + _MONTH_WORD + r"\b")),
)
_NUMBERS = {None: 1, "": 1, "одну": 1, "один": 1, "две": 2, "два": 2, "три": 3, "пару": 2}

# «Я бросил курить», «Я больше не работаю в Яндексе» — старое утверждение закрывается.
CHANGE = re.compile(
    r"(?iu)^\s*(?:я\s+)?(?:(?:бросил|бросила|перестал|перестала|завязал|завязала)\s+"
    r"|(?:больше|уже)\s+не\s+|не\s+(?:работаю|живу|учусь|занимаюсь|изучаю|хожу)\b\s*)"
    r"(?P<rest>.{2,200})$"
)
_PRONOUN = re.compile(r"(?iu)^\s*(он|она|они)\b")
_PERSON = re.compile(
    r"(?iu)\b(?:мо[йяи]|наш[аи]?)\s+(?:лучш\w+\s+)?"
    r"(брат\w*|сестр\w*|друг\w*|подруг\w*|мам\w*|пап\w*|жен\w*|муж\w*|сын\w*|доч\w*|"
    r"коллег\w*|начальни\w*|руководител\w*|парен\w*|девушк\w*|бабушк\w*|дедушк\w*)"
    r"(?:\s+(?P<name>[А-ЯЁA-Z][а-яёa-z]+))?"
)
_FEMININE = re.compile(r"(?iu)^(сестр|подруг|мам|жен|доч|девушк|бабушк)")


@lru_cache(maxsize=1)
def _morph():
    return pymorphy3.MorphAnalyzer() if pymorphy3 else None


@lru_cache(maxsize=50_000)
def lemma(word: str) -> str | None:
    """Начальная форма слова или None, если лемматизатор не установлен."""
    morph = _morph()
    if morph is None or not re.search(r"[а-яё]", word):
        return None
    return morph.parse(word)[0].normal_form


@lru_cache(maxsize=50_000)
def is_noun(word: str) -> bool:
    morph = _morph()
    return bool(morph and morph.parse(word)[0].tag.POS == "NOUN")


def statements(text: str) -> list[str]:
    """Утверждения сообщения: без вопросов, приветствий и пустых реплик."""
    result = []
    for part in _SENTENCE.split(text.strip()):
        part = part.strip()
        while True:
            stripped = _FILLER.sub("", part, count=1)
            if stripped == part:
                break
            part = stripped.strip()
        if not part or part.endswith("?") or len(part) < 4:
            continue
        result.append(part.rstrip(".!;… ").strip())
    return [s for s in result if s]


def without_lead_time(text: str) -> str:
    return _LEAD_TIME.sub("", text, count=1)


def _local_day(stamp_ms: int) -> date:
    return datetime.fromtimestamp(stamp_ms / 1000, tz=timezone.utc).astimezone().date()


def due_date(text: str, sent_at_ms: int) -> date | None:
    """Срок из относительной даты: «завтра», «в пятницу», «через неделю», «к декабрю»."""
    today = _local_day(sent_at_ms)
    for kind, pattern in _DATE_PATTERNS:
        found = pattern.search(text)
        if not found:
            continue
        if kind == "relative_day":
            return today + timedelta(days={"сегодня": 0, "завтра": 1, "послезавтра": 2}[found.group(1).casefold()])
        if kind == "weekday":
            word = found.group(1).casefold()
            target = next(v for k, v in _WEEKDAYS.items() if word.startswith(k))
            ahead = (target - today.weekday()) % 7 or 7
            if "следующ" in found.group(0).casefold():
                ahead += 7 if ahead < 7 else 0
            return today + timedelta(days=ahead)
        if kind == "in_units":
            count = int(found.group(1)) if (found.group(1) or "").isdigit() else _NUMBERS.get(found.group(1), 1)
            unit = found.group(2).casefold()
            if unit.startswith("д"):
                return today + timedelta(days=count)
            if unit.startswith("недел"):
                return today + timedelta(weeks=count)
            if unit.startswith("месяц"):
                return _add_months(today, count)
            return _add_months(today, 12 * count)
        if kind == "day_month":
            return _upcoming(today, _month(found.group(2)), int(found.group(1)))
        if kind == "numeric":
            day, month, year = int(found.group(1)), int(found.group(2)), found.group(3)
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue
            if year:
                year = int(year) + (2000 if len(year) == 2 else 0)
                return _safe(year, month, day)
            return _upcoming(today, month, day)
        if kind == "month":
            month = _month(found.group(1))
            # «к декабрю» — к началу месяца, «в декабре» — тоже первое число как ориентир.
            return _upcoming(today, month, 1)
    return None


def _month(word: str) -> int:
    word = word.casefold()
    return next(v for k, v in sorted(_MONTHS.items(), key=lambda x: -len(x[0])) if word.startswith(k))


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _upcoming(today: date, month: int, day: int) -> date | None:
    value = _safe(today.year, month, day)
    if value and value < today:
        value = _safe(today.year + 1, month, day)
    return value


def _add_months(today: date, count: int) -> date:
    month = today.month - 1 + count
    year = today.year + month // 12
    month = month % 12 + 1
    for day in (today.day, 30, 29, 28):
        value = _safe(year, month, day)
        if value:
            return value
    return today


def change_topic(text: str) -> str | None:
    """Что закончилось: «Я бросил курить» → «курить»."""
    found = CHANGE.match(without_lead_time(text))
    return found.group("rest").strip() if found else None


def person_in(text: str) -> tuple[str, bool] | None:
    """Последний названный человек: («Петя (брат)», женский род?)."""
    found = None
    for found in _PERSON.finditer(text):
        pass
    if not found:
        return None
    role = found.group(1).casefold()
    role_word = lemma(role) or role
    label = f"{found.group('name')} ({role_word})" if found.group("name") else role_word.capitalize()
    return label, bool(_FEMININE.match(role))


def resolve_pronoun(statement: str, before: str) -> str | None:
    """«Он хочет в Питер» после «Мой брат Петя…» → «Петя (брат) хочет в Питер»."""
    found = _PRONOUN.match(statement)
    if not found:
        return None
    person = person_in(before)
    if not person:
        return None
    label, feminine = person
    pronoun = found.group(1).casefold()
    if pronoun == "они" or (pronoun == "она") != feminine:
        return None
    return label + statement[found.end():]
