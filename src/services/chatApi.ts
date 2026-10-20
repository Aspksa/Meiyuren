import type { Message } from '../store/useAppStore';

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === 'object' && 'detail' in body ? String(body.detail) : '';
    throw new Error(detail || 'Python-сервер недоступен. Запустите setup-python.cmd и перезапустите Meiyuren.cmd.');
  }
  return response.json() as Promise<T>;
}

export async function loadHistory(signal?: AbortSignal): Promise<Message[]> {
  const response = await fetch('/api/chat/messages?limit=200', { cache: 'no-store', signal });
  return (await parse<{ messages: Message[] }>(response)).messages;
}

export async function sendMessage(text: string): Promise<{ user: Message; assistant: Message }> {
  return parse(await fetch('/api/chat/messages', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
  }));
}

export async function clearHistory(): Promise<void> {
  await parse<{ deleted: number }>(await fetch('/api/chat/messages', { method: 'DELETE' }));
}

export async function loadMemory(signal?: AbortSignal): Promise<string> {
  const response = await fetch('/api/memory', { signal, cache: 'no-store' });
  return (await parse<{ notes: string }>(response)).notes;
}

export async function saveMemory(notes: string): Promise<void> {
  await parse(await fetch('/api/memory', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes }),
  }));
}
