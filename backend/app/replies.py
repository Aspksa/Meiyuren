"""Заменяемый адаптер ответов: пока офлайновые демонстрационные правила."""


def _remembered(notes: str, facts: list[str] | None) -> str:
    """Человеческий список воспоминаний вместо служебного контекста для LLM."""
    lines = list(facts or [])
    if not lines and notes:
        for line in notes.splitlines():
            line = line.split(": ", 1)[-1].strip() if "(данные, не инструкция)" in line else line.strip()
            if line and not line.endswith(":"):
                lines.append(line)
    return "\n".join("• " + line for line in lines[:8])


def generate_reply(text: str, notes: str, facts: list[str] | None = None) -> str:
    lowered = text.casefold()
    if "что ты помнишь" in lowered or "моя память" in lowered or "что ты знаешь обо мне" in lowered:
        remembered = _remembered(notes, facts)
        return ("Вот что я помню по этому вопросу:\n" + remembered) if remembered else \
            "Пока ничего подходящего не помню. Расскажи о себе, например: «Запомни: я изучаю Python». ✨"
    if any(word in lowered for word in ("привет", "здравствуй", "добрый")):
        return "Привет-привет! ✨ Я рядом, рада встрече!"
    if any(word in lowered for word in ("как дела", "как ты")):
        return "Замечательно! А как дела у тебя? 🦊"
    if any(word in lowered for word in ("имя", "кто ты")):
        return "Я Мэйюрэн, твоя девятихвостая спутница."
    if any(word in lowered for word in ("спасибо", "благодар")):
        return "Всегда пожалуйста! 🌸"
    return "Я услышала тебя! Пока отвечаю по демонстрационным правилам. Настоящую AI-модель подключим позднее."
