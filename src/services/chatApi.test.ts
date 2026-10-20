import { describe, expect, it, vi } from 'vitest';
import { consumeSSE } from './chatApi';

function streamParts(parts: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part));
      controller.close();
    },
  });
}

describe('SSE protocol Cloud.ru', () => {
  it('обрабатывает несколько произвольных блоков, включая границы UTF-8', async () => {
    const body = 'event: delta\ndata: {"text":"Привет"}\n\n' +
      'event: delta\ndata: {"text":" 🌸"}\n\n' +
      'event: done\ndata: {"user":{"id":"1"},"assistant":{"id":"2","text":"Привет 🌸"}}\n\n';
    const chunks = [body.slice(0, 9), body.slice(9, 30), body.slice(30)];
    const parts: string[] = [];
    const result = await consumeSSE(streamParts(chunks), text => parts.push(text));
    expect(parts.join('')).toBe('Привет 🌸');
    expect(result.assistant.text).toBe('Привет 🌸');
  });

  it('показывает понятную ошибку из события error', async () => {
    const onDelta = vi.fn();
    await expect(consumeSSE(streamParts(['event: error\ndata: {"message":"Ошибка Cloud.ru"}\n\n']), onDelta))
      .rejects.toThrow('Ошибка Cloud.ru');
    expect(onDelta).not.toHaveBeenCalled();
  });

  it('не выдаёт неполный ответ за сохранённый', async () => {
    await expect(consumeSSE(streamParts(['event: delta\ndata: {"text":"Часть"}\n\n']), () => undefined))
      .rejects.toThrow('без подтверждения');
  });
});
