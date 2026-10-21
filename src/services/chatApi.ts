import type { Message } from '../store/useAppStore';

export type Conversation = { id: string; title: string; createdAt: number; updatedAt: number };
export type MemoryBrain = 'identity' | 'episodes' | 'goals' | 'habits' | 'knowledge';
export type MemoryNetwork = {
  brains: Record<MemoryBrain, number>; links: number; neuralVectors: number;
  embeddingModel: string; embeddingDimensions: number;
};
export type MemoryConnection = { item: MemoryFact; relation: 'shared_topic' | 'neural_similarity'; weight: number };
export type MemoryNeuralMatch = { item: MemoryFact; similarity: number };
export type MemoryFact = {
  id: string; content: string; createdAt: number; updatedAt: number;
  kind: string; status: string; sourceMessageId: string | null;
  conversationId: string; cloudAllowed: boolean; expiresAt: number | null; revision: number; brain: MemoryBrain;
};
export type MemoryCandidate = {
  id: string; content: string; sourceMessageId: string; conversationId: string; createdAt: number;
  conflictWith: string | null; brain: MemoryBrain;
};
export type MemorySummary = {
  conversationId: string; content: string; status: string; cloudAllowed: boolean; updatedAt: number;
};
export type MemoryPolicy = {
  allow_cloud_notes: boolean; allow_cloud_facts: boolean;
  auto_extract: boolean; auto_summaries: boolean; allow_cloud_embeddings: boolean;
};
export type MemoryStatus = {
  facts: number; pending: number; jobs: number; summaries: number; policy: MemoryPolicy; network: MemoryNetwork;
};
export type MemoryExplanation = {
  item: MemoryFact; source: { id: string; text: string } | null; sourceAvailable: boolean;
  revisions: { revision: number; action: string; content: string; createdAt: number }[];
};
export type MemoryRecallPreview = { memories: MemoryFact[]; context: string };
export type MemoryUsage = { memoryId: string; conversationId: string; cloudMode: boolean; selectedAt: number; content: string };
export type ChatMatch = Message & { conversationId: string };
export type Exchange = { user: Message; assistant: Message };

export async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    const message = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    throw new Error(typeof message === 'string' ? message : 'Python-сервер недоступен. Проверьте Meiyuren.cmd.');
  }
  return response.json() as Promise<T>;
}

const headers = { 'Content-Type': 'application/json', 'X-Meiyuren-Client': '1' };

export async function loadHistory(conversationId = 'main', signal?: AbortSignal): Promise<Message[]> {
  return (await parse<{ messages: Message[] }>(await fetch('/api/chat/messages?limit=200&conversationId=' + encodeURIComponent(conversationId),
    { cache: 'no-store', signal }))).messages;
}

export async function clearHistory(conversationId = 'main'): Promise<void> {
  await parse(await fetch('/api/chat/messages?conversationId=' + encodeURIComponent(conversationId),
    { method: 'DELETE', headers }));
}

export async function loadMemory(signal?: AbortSignal): Promise<string> {
  return (await parse<{ notes: string }>(await fetch('/api/memory', { signal, cache: 'no-store' }))).notes;
}

export async function saveMemory(notes: string): Promise<void> {
  await parse(await fetch('/api/memory', { method: 'PUT', headers, body: JSON.stringify({ notes }) }));
}

export async function getConversations(): Promise<Conversation[]> {
  return (await parse<{ conversations: Conversation[] }>(await fetch('/api/conversations', { cache: 'no-store' }))).conversations;
}

export async function createConversation(title: string): Promise<Conversation> {
  return parse(await fetch('/api/conversations', { method: 'POST', headers, body: JSON.stringify({ title }) }));
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await parse(await fetch('/api/conversations/' + encodeURIComponent(id), { method: 'PUT', headers, body: JSON.stringify({ title }) }));
}

export async function deleteConversation(id: string): Promise<void> {
  await parse(await fetch('/api/conversations/' + encodeURIComponent(id), { method: 'DELETE', headers }));
}

export async function searchChat(q: string, conversationId?: string): Promise<ChatMatch[]> {
  const query = '?q=' + encodeURIComponent(q) + (conversationId ? '&conversationId=' + encodeURIComponent(conversationId) : '');
  return (await parse<{ matches: ChatMatch[] }>(await fetch('/api/chat/search' + query, { cache: 'no-store' }))).matches;
}

export async function getMemoryFacts(): Promise<MemoryFact[]> {
  return (await parse<{ facts: MemoryFact[] }>(await fetch('/api/memory/facts', { cache: 'no-store' }))).facts;
}
export async function addMemoryFact(
  content: string, cloudAllowed = false, brain: MemoryBrain | null = null,
): Promise<MemoryFact> {
  return parse(await fetch('/api/memory/facts', { method: 'POST', headers, body: JSON.stringify({ content, cloudAllowed, brain }) }));
}

export async function updateMemoryFact(
  fact: MemoryFact, content: string, cloudAllowed: boolean, expiresAt: number | null = fact.expiresAt,
  brain: MemoryBrain = fact.brain,
): Promise<MemoryFact> {
  return parse(await fetch('/api/memory/facts/' + encodeURIComponent(fact.id), {
    method: 'PUT', headers, body: JSON.stringify({ content, cloudAllowed, revision: fact.revision, expiresAt, brain }),
  }));
}

export async function explainMemoryFact(id: string): Promise<MemoryExplanation> {
  return parse(await fetch('/api/memory/facts/' + encodeURIComponent(id) + '/explain', { cache: 'no-store' }));
}

export async function previewMemoryRecall(
  query: string, conversationId = 'main', cloudMode = true,
): Promise<MemoryRecallPreview> {
  const args = new URLSearchParams({ q: query, conversationId, cloudMode: String(cloudMode) });
  return parse(await fetch('/api/memory/recall?' + args.toString(), { cache: 'no-store' }));
}

export async function getMemoryUsage(): Promise<MemoryUsage[]> {
  return (await parse<{ entries: MemoryUsage[] }>(
    await fetch('/api/memory/usage', { cache: 'no-store' }),
  )).entries;
}

export async function getMemoryBrains(): Promise<MemoryNetwork> {
  return parse(await fetch('/api/memory/brains', { cache: 'no-store' }));
}

export async function getMemoryBrainLinks(id: string): Promise<MemoryConnection[]> {
  return (await parse<{ connections: MemoryConnection[] }>(
    await fetch('/api/memory/brains/' + encodeURIComponent(id) + '/links', { cache: 'no-store' }),
  )).connections;
}

export async function indexMemoryNeural(itemId: string, requestId: string): Promise<{ status: string; cached: boolean }> {
  return parse(await fetch('/api/memory/neural/index', {
    method: 'POST', headers, body: JSON.stringify({ itemId, requestId }),
  }));
}

export async function searchMemoryNeural(
  q: string, requestId: string, conversationId = 'main',
): Promise<MemoryNeuralMatch[]> {
  return (await parse<{ matches: MemoryNeuralMatch[] }>(
    await fetch('/api/memory/neural/search', {
      method: 'POST', headers, body: JSON.stringify({ q, requestId, conversationId }),
    }),
  )).matches;
}

export async function clearMemoryNeuralVectors(): Promise<number> {
  return (await parse<{ deleted: number }>(
    await fetch('/api/memory/neural/vectors', { method: 'DELETE', headers }),
  )).deleted;
}

export async function getMemoryStatus(): Promise<MemoryStatus> {
  return parse(await fetch('/api/memory/status', { cache: 'no-store' }));
}

export async function getMemoryPolicy(): Promise<MemoryPolicy> {
  return parse(await fetch('/api/memory/policy', { cache: 'no-store' }));
}

export async function setMemoryPolicy(patch: Partial<MemoryPolicy>): Promise<MemoryPolicy> {
  return parse(await fetch('/api/memory/policy', { method: 'PUT', headers, body: JSON.stringify(patch) }));
}

export async function getMemoryCandidates(): Promise<MemoryCandidate[]> {
  return (await parse<{ candidates: MemoryCandidate[] }>(await fetch('/api/memory/candidates', { cache: 'no-store' }))).candidates;
}

export async function reviewMemoryCandidate(id: string, approve: boolean, cloudAllowed = false): Promise<void> {
  await parse(await fetch('/api/memory/candidates/' + encodeURIComponent(id) + '/review', {
    method: 'POST', headers, body: JSON.stringify({ approve, cloudAllowed }),
  }));
}

export async function getMemorySummaries(): Promise<MemorySummary[]> {
  return (await parse<{ summaries: MemorySummary[] }>(await fetch('/api/memory/summaries', { cache: 'no-store' }))).summaries;
}

export async function reviewMemorySummary(id: string, approve: boolean, cloudAllowed = false): Promise<void> {
  await parse(await fetch('/api/memory/summaries/' + encodeURIComponent(id) + '/review', {
    method: 'POST', headers, body: JSON.stringify({ approve, cloudAllowed }),
  }));
}

export async function processMemoryJobs(): Promise<MemoryStatus & { processed: number }> {
  return parse(await fetch('/api/memory/process', { method: 'POST', headers }));
}
export async function removeMemoryFact(id: string): Promise<void> {
  await parse(await fetch('/api/memory/facts/' + encodeURIComponent(id), { method: 'DELETE', headers }));
}

export async function consumeSSE(
  stream: ReadableStream<Uint8Array>,
  onDelta: (part: string) => void,
): Promise<Exchange> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        const event = /^event:\s*(.+)$/m.exec(frame)?.[1]?.trim();
        const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n');
        if (!data) continue;
        const payload: unknown = JSON.parse(data);
        if (event === 'delta' && payload && typeof payload === 'object' && 'text' in payload) {
          const part = payload.text;
          if (typeof part === 'string') onDelta(part);
        } else if (event === 'error') {
          const message = payload && typeof payload === 'object' && 'message' in payload ? payload.message : null;
          throw new Error(typeof message === 'string' ? message : 'Ошибка потокового ответа.');
        } else if (event === 'done') {
          return payload as Exchange;
        }
      }
    }
    throw new Error('Поток завершился без подтверждения результата. Повтор того же запроса безопаснее нового.');
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function streamMessage(
  text: string, requestId: string, conversationId: string,
  onDelta: (part: string) => void, signal?: AbortSignal,
): Promise<Exchange> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST', headers,
    body: JSON.stringify({ text, requestId, conversationId }), signal, cache: 'no-store',
  });
  if (!response.ok) await parse(response);
  if (!response.body) throw new Error('Браузер не поддерживает потоковый ответ.');
  return consumeSSE(response.body, onDelta);
}
