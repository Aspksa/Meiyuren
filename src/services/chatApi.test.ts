import { describe, expect, it, vi } from 'vitest';
import { consumeSSE, describeIdleReport, StreamError } from './chatApi';

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

  it('передаёт режим, признак оплаты и сохранённую часть ответа', async () => {
    const saved = '{"user":{"id":"u"},"assistant":{"id":"a","text":"Часть [прервано]"},"interrupted":true}';
    const error = await consumeSSE(streamParts([
      'event: delta\ndata: {"text":"Часть"}\n\n',
      'event: error\ndata: {"message":"Обрыв","mode":"cloud","paid":true,"saved":' + saved + '}\n\n',
    ]), () => undefined).catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(StreamError);
    expect((error as StreamError).mode).toBe('cloud');
    expect((error as StreamError).saved?.assistant.id).toBe('a');
  });

  it('в демо-режиме ошибка не считается платной', async () => {
    const error = await consumeSSE(streamParts(['event: error\ndata: {"message":"Сбой","mode":"demo","paid":false}\n\n']),
      () => undefined).catch((cause: unknown) => cause);
    expect((error as StreamError).paid).toBe(false);
    expect((error as StreamError).saved).toBeNull();
  });
});

describe('describeIdleReport', () => {
  it('turns an idle run into readable lines and skips empty steps', () => {
    const lines = describeIdleReport({
      consolidation: { merged: 2, conflicts: [['Я люблю кофе', 'Я не люблю кофе']] },
      strength: { facts: 10, strong: 3, fading: 1 },
      selfTraining: { strategy: 'balanced', benchmark: 'self_retrieval_proxy', cases: 0 },
      vectors: { updated: 0, total: 10 },
      health: { integrity: 'ok', backup: 'meiyuren-2026-10-21.sqlite3' },
    });
    expect(lines[0]).toContain('2');
    expect(lines[1]).toContain('Противоречие');
    expect(lines.some(line => line.includes('поиск на твоих оценках'))).toBe(false);
    expect(lines.some(line => line.includes('нечёткий'))).toBe(false);
    expect(lines.at(-1)).toContain('резервная копия');
  });
});
