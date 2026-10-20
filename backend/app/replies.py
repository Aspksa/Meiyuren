"""Заменяемый адаптер ответов: пока офлайновые демонстрационные правила."""


def generate_reply(text: str, notes: str) -> str:
    lowered = text.casefold()
    if "что ты помнишь" in lowered or "моя память" in lowered:
        return f"Ты сохранил(а) для меня: {notes}" if notes else "В моей памяти пока пусто. Добавь заметку в настройках! ✨"
    if any(word in lowered for word in ("привет", "здравствуй", "добрый")):
        return "Привет-привет! ✨ Я рядом, рада встрече!"
    if any(word in lowered for word in ("как дела", "как ты")):
        return "Замечательно! А как дела у тебя? 🦊"
    if any(word in lowered for word in ("имя", "кто ты")):
        return "Я Мэйюрэн, твоя девятихвостая спутница."
    if any(word in lowered for word in ("спасибо", "благодар")):
        return "Всегда пожалуйста! 🌸"
    return "Я услышала тебя! Пока отвечаю по демонстрационным правилам. Настоящую AI-модель подключим позднее."
