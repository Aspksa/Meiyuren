// Демо-ответы: никаких внешних запросов и API-ключей на клиенте.
export function getDemoReply(input: string): string {
  const text = input.toLocaleLowerCase('ru-RU');
  if (/привет|здравствуй|добрый/.test(text)) {
    return 'Привет-привет! ✨ Я рядом. Хочешь поболтать?';
  }
  if (/как дела|как ты/.test(text)) {
    return 'Замечательно! Мои девять хвостов сегодня особенно пушистые. А как твои дела?';
  }
  if (/имя|кто ты/.test(text)) {
    return 'Я Мэйюрэн — твоя маленькая девятихвостая спутница в этом приложении. 🦊';
  }
  if (/помощ|что умеешь|команд/.test(text)) {
    return 'Пока я умею общаться в демо-чате, перемещаться по экрану и менять настройки. Скоро возможностей станет больше!';
  }
  if (/спасибо|благодар/.test(text)) {
    return 'Всегда пожалуйста! 🌸';
  }
  return 'Я услышала тебя. 🌸 Пока у меня демонстрационные ответы, а полноценный AI-чат мы подключим позже.';
}

export function replyAfterDelay(input: string): Promise<string> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(getDemoReply(input)), 420);
  });
}
