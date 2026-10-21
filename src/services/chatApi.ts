import type { Message } from '../store/useAppStore';

export type Conversation = { id: string; title: string; createdAt: number; updatedAt: number };
export type MemoryBrain =
  | 'identity' | 'episodes' | 'goals' | 'habits' | 'knowledge'
  | 'relationships' | 'projects' | 'decisions';
export type MemoryNetwork = {
  brains: Record<MemoryBrain, number>; links: number; neuralVectors: number;
  embeddingModel: string; embeddingDimensions: number;
};
export type MemoryBranch = {
  id: string; parentId: string | null; brain: MemoryBrain; term: string;
  title: string; depth: number; support: number;
};
export type MemoryTree = { roots: MemoryBrain[]; custom?: { id: string; title: string }[]; branches: MemoryBranch[] };
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
  auto_growth: boolean; auto_evolution: boolean; semantic_model?: boolean;
  curiosity?: boolean;
};
export type MemoryEvolution = {
  generation: number; strategy: string; evaluations: number; lastEvaluated: number;
  microbrains: number; adaptiveSynapses: number; automatic: boolean;
  benchmark?: 'feedback' | 'self_retrieval_proxy' | 'none'; feedbackCases?: number;
};
export type CortexStatus = {
  roots: number; edges: number; connectedBrains: number; brainPairs: number;
  evaluation: { cases: number; baselineHits: number; meshHits: number; evaluatedAt: number };
};
export type CortexProvenance = {
  confirmed: number; sourceBacked: number; withoutMessageSource: number;
  potentialPreferenceConflicts: number;
};
export type CortexConnection = {
  item: DeepMemoryFact; fromBrain: MemoryBrain; toBrain: MemoryBrain;
  sharedTerms: number; strength: number; relation: 'shared_evidence';
};
export type MemoryStatus = {
  facts: number; pending: number; jobs: number; summaries: number;
  policy: MemoryPolicy; network: MemoryNetwork; autonomousBranches: number;
  evolution: MemoryEvolution; cortex: CortexStatus;
};
export type MemoryExplanation = {
  item: MemoryFact; source: { id: string; text: string } | null; sourceAvailable: boolean;
  revisions: { revision: number; action: string; content: string; createdAt: number }[];
};
export type DeepMemoryFact = MemoryFact & {
  eventType: string; eventState: string; observedAt: number; statedReason: string | null;
  helpful: number; unhelpful: number;
};
export type DeepMemoryBrain = { brain: MemoryBrain; count: number; short: string[]; detailed: DeepMemoryFact[] };
export type DeepMemoryOverview = {
  brains: DeepMemoryBrain[]; timeline: DeepMemoryFact[]; continuation: DeepMemoryFact[];
  decisions: DeepMemoryFact[]; count: number; cloudMode: boolean;
};
export type DeepMemoryMetrics = {
  indexedEvents: number; search: { intent: string; searches: number; hits: number }[];
};
export type MemoryEpisode = {
  id: string; day: string; conversationId: string;
  observedStart: number; observedEnd: number;
  short: string[]; facts: DeepMemoryFact[];
};
export type MemoryProjectCheckpoint = {
  memoryId: string; projectKey: string; state: string;
  observedAt: number; content: string; brain: MemoryBrain;
};
export type EpisodicMemoryOverview = {
  episodes: MemoryEpisode[]; checkpoints: MemoryProjectCheckpoint[];
  continuation: MemoryProjectCheckpoint[];
  explicitEventDates: { memoryId: string; eventDay: string; observationAt: number }[];
  count: number; cloudMode: boolean;
};
export type MemoryRecallPreview = { memories: MemoryFact[]; context: string };
export type MemoryUsage = { memoryId: string; conversationId: string; cloudMode: boolean; selectedAt: number; content: string };
export type ChatMatch = Message & { conversationId: string };
export type RecallMemory = { id: string; content: string; brain: MemoryBrain };
export type Inference = {
  id: string; kind: 'chain' | 'time' | 'overdue' | 'conflict' | 'helps' | 'rule';
  content: string; confidence: number; ask: boolean; because: RecallMemory[];
};
export type RecallTrace = { traceId: string; items: RecallMemory[]; inferences?: Inference[] };
export type Curiosity = { id: string; question: string };
export type Exchange = {
  user: Message; assistant: Message; memory?: RecallTrace; curiosity?: Curiosity; interrupted?: boolean;
};

/** Ошибка потока с режимом: в демо-режиме нет платных повторов и предупреждений об оплате. */
export class StreamError extends Error {
  constructor(message: string, readonly mode: 'cloud' | 'demo' | null, readonly paid: boolean,
    readonly saved: Exchange | null) {
    super(message);
    this.name = 'StreamError';
  }
}

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

export async function rebuildMemoryBrainLinks(): Promise<number> {
  return (await parse<{ links: number }>(await fetch('/api/memory/brains/rebuild', {
    method: 'POST', headers,
  }))).links;
}

export async function getMemoryTree(): Promise<MemoryTree> {
  return parse(await fetch('/api/memory/tree', { cache: 'no-store' }));
}

export async function rebuildMemoryTree(): Promise<{ roots: number; branches: number; scanned: number }> {
  return parse(await fetch('/api/memory/tree/rebuild', { method: 'POST', headers }));
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

export async function getEpisodicMemoryOverview(
  conversationId = 'main', cloudMode = false,
): Promise<EpisodicMemoryOverview> {
  const args = new URLSearchParams({ conversationId, cloudMode: String(cloudMode) });
  return parse(await fetch('/api/memory/episodes?' + args.toString(), { cache: 'no-store' }));
}

export async function rebuildEpisodicMemory(): Promise<{
  episodes: number; checkpoints: number; indexedFacts: number;
}> {
  return parse(await fetch('/api/memory/episodes/rebuild', { method: 'POST', headers }));
}

export async function getDeepMemoryOverview(
  conversationId = 'main', cloudMode = false,
): Promise<DeepMemoryOverview> {
  const params = new URLSearchParams({ conversationId, cloudMode: String(cloudMode) });
  return parse(await fetch('/api/memory/deep/overview?' + params.toString(), { cache: 'no-store' }));
}

export async function getDeepMemoryMetrics(): Promise<DeepMemoryMetrics> {
  return parse(await fetch('/api/memory/deep/metrics', { cache: 'no-store' }));
}

export async function rebuildDeepMemoryIndex(): Promise<{ indexed: number; outlines: number }> {
  return parse(await fetch('/api/memory/deep/rebuild', { method: 'POST', headers }));
}

export async function sendDeepMemoryFeedback(
  memoryId: string, helpful: boolean,
): Promise<{ memoryId: string; helpful: number; unhelpful: number }> {
  return parse(await fetch('/api/memory/deep/facts/' + encodeURIComponent(memoryId) + '/feedback', {
    method: 'POST', headers, body: JSON.stringify({ helpful }),
  }));
}

export async function getCortexMesh(
  conversationId = 'main', cloudMode = false,
): Promise<CortexStatus & { provenance: CortexProvenance }> {
  const params = new URLSearchParams({ conversationId, cloudMode: String(cloudMode) });
  return parse(await fetch('/api/memory/cortex?' + params.toString(), { cache: 'no-store' }));
}

export async function getCortexConnections(
  id: string, conversationId = 'main', cloudMode = false,
): Promise<{ connections: CortexConnection[] }> {
  const params = new URLSearchParams({ conversationId, cloudMode: String(cloudMode) });
  return parse(await fetch('/api/memory/cortex/facts/' + encodeURIComponent(id) + '/connections?' +
    params.toString(), { cache: 'no-store' }));
}

export async function evaluateCortexMesh(): Promise<{
  cases: number; baselineHits: number; meshHits: number;
}> {
  return parse(await fetch('/api/memory/cortex/evaluate', { method: 'POST', headers }));
}

export async function getMemoryEvolution(): Promise<MemoryEvolution> {
  return parse(await fetch('/api/memory/evolution', { cache: 'no-store' }));
}

export async function resetMemoryEvolution(): Promise<MemoryEvolution> {
  return parse(await fetch('/api/memory/evolution/reset', { method: 'POST', headers }));
}

export async function evaluateMemoryEvolution(): Promise<MemoryEvolution> {
  return parse(await fetch('/api/memory/evolution/evaluate', { method: 'POST', headers }));
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
          const info = (payload && typeof payload === 'object' ? payload : {}) as
            { message?: unknown; mode?: unknown; paid?: unknown; saved?: unknown };
          const mode = info.mode === 'cloud' || info.mode === 'demo' ? info.mode : null;
          throw new StreamError(typeof info.message === 'string' ? info.message : 'Ошибка потокового ответа.',
            mode, info.paid !== false, info.saved && typeof info.saved === 'object' ? info.saved as Exchange : null);
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

export async function loadOlderHistory(conversationId: string, beforeId: string, limit = 100): Promise<Message[]> {
  const args = new URLSearchParams({ conversationId, before: beforeId, limit: String(limit) });
  return (await parse<{ messages: Message[] }>(await fetch('/api/chat/messages?' + args.toString(), { cache: 'no-store' }))).messages;
}

export async function getEngineMode(): Promise<'cloud' | 'demo'> {
  const data = await parse<{ engine: string }>(await fetch('/api/health', { cache: 'no-store' }));
  return data.engine === 'cloud' ? 'cloud' : 'demo';
}

export async function rateRecalledMemory(traceId: string, memoryId: string, helpful: boolean): Promise<void> {
  await parse(await fetch('/api/memory/recall/' + encodeURIComponent(traceId) + '/feedback', {
    method: 'POST', headers, body: JSON.stringify({ memoryId, helpful }),
  }));
}

export type CloudBrains = { brains: Record<MemoryBrain, boolean>; enabled: boolean };

export async function getCloudBrains(): Promise<CloudBrains> {
  return parse(await fetch('/api/memory/cloud-brains', { cache: 'no-store' }));
}

export async function setCloudBrains(brains: Partial<Record<MemoryBrain, boolean>>): Promise<CloudBrains> {
  return parse(await fetch('/api/memory/cloud-brains', { method: 'PUT', headers, body: JSON.stringify({ brains }) }));
}

export type IdleReport = {
  consolidation?: { merged: number; conflicts: string[][] };
  strength?: { facts: number; strong: number; fading: number };
  selfTraining?: { strategy: string; benchmark?: string; cases: number };
  unfinished?: { items: string[] };
  vectors?: { updated: number; total: number };
  health?: { integrity: string; backup: string | null };
};
export type IdleBriefing = { id: string; startedAt: number; finishedAt: number; interrupted: boolean; report: IdleReport };

/** Отчёт режима простоя «Пока тебя не было», если он ещё не показан. */
export async function getIdleBriefing(): Promise<IdleBriefing | null> {
  return (await parse<{ briefing: IdleBriefing | null }>(await fetch('/api/idle/briefing', { cache: 'no-store' }))).briefing;
}

export async function markIdleBriefingSeen(): Promise<void> {
  await parse(await fetch('/api/idle/seen', { method: 'POST', headers }));
}

/** Человекочитаемые строки отчёта; пустые шаги пропускаются. */
export function describeIdleReport(report: IdleReport): string[] {
  const lines: string[] = [];
  const merged = report.consolidation?.merged ?? 0;
  if (merged) lines.push(`Объединила повторы в памяти: ${merged}.`);
  for (const [yes, no] of report.consolidation?.conflicts ?? []) lines.push(`Противоречие: «${yes}» и «${no}». Что из этого верно?`);
  if (report.strength?.facts) {
    lines.push(`Пересчитала силу фактов: крепких ${report.strength.strong}, тускнеющих ${report.strength.fading}.`);
  }
  if (report.selfTraining?.benchmark === 'feedback') {
    lines.push(`Потренировала поиск на твоих оценках (${report.selfTraining.cases}), стратегия: ${report.selfTraining.strategy}.`);
  }
  if (report.vectors?.updated) lines.push(`Обновила локальный нечёткий поиск: ${report.vectors.updated} фактов.`);
  if (report.health) {
    lines.push(report.health.integrity === 'ok'
      ? `База в порядке${report.health.backup ? ', резервная копия сделана' : ''}.`
      : 'Проверка базы нашла проблему: стоит открыть настройки памяти.');
  }
  return lines;
}

export type MemoryEntity = { id: string; kind: 'person' | 'project' | 'place' | 'org' | 'tool'; name: string; role: string | null; facts: number };
export type MemoryEntityDetail = Omit<MemoryEntity, 'facts'> & {
  facts: MemoryFact[]; related: { id: string; kind: MemoryEntity['kind']; name: string; shared: number }[];
};
export type SemanticStatus = { model: string; state: string; downloaded: boolean; error: string | null; enabled: boolean };

/** Граф памяти: люди, проекты, места, организации и инструменты из фактов. */
export async function getMemoryEntities(): Promise<MemoryEntity[]> {
  return (await parse<{ entities: MemoryEntity[] }>(await fetch('/api/memory/entities', { cache: 'no-store' }))).entities;
}

export async function getMemoryEntity(id: string): Promise<MemoryEntityDetail> {
  return parse(await fetch('/api/memory/entities/' + encodeURIComponent(id), { cache: 'no-store' }));
}

export async function getSemanticStatus(): Promise<SemanticStatus> {
  return parse(await fetch('/api/memory/semantic', { cache: 'no-store' }));
}

export type BrainBranchState = { id: string; title: string; support: number; depth: number; strength: number };
export type BrainMapRoot = {
  id: string; title: string | null; custom: boolean; facts: number; growth: number;
  branches: number; newBranches: number; strong: BrainBranchState[]; sleeping: BrainBranchState[];
};
export type BrainProposal = { id: string; title: string; term: string; support: number; brains: MemoryBrain[] };
export type BrainMap = { roots: BrainMapRoot[]; proposals: BrainProposal[] };

/** Карта мозгов: рост за неделю, сильные и засыпающие ветки, предложения новых мозгов. */
export async function getBrainMap(): Promise<BrainMap> {
  return parse(await fetch('/api/memory/brains/map', { cache: 'no-store' }));
}

export async function decideBrainProposal(id: string, accept: boolean): Promise<{ accepted: boolean; title: string }> {
  return parse(await fetch('/api/memory/brains/proposals/' + encodeURIComponent(id),
    { method: 'POST', headers, body: JSON.stringify({ accept }) }));
}

export async function removeCustomBrain(id: string): Promise<void> {
  await parse(await fetch('/api/memory/brains/custom/' + encodeURIComponent(id), { method: 'DELETE', headers }));
}

/** «Не спрашивать об этом»: вопрос любопытства больше не появится. */
export async function dismissCuriosity(id: string): Promise<void> {
  await parse(await fetch('/api/memory/curiosity/' + encodeURIComponent(id) + '/dismiss', { method: 'POST', headers }));
}

/** Логический мозг: выводы из фактов с основаниями. */
export async function getInferences(): Promise<Inference[]> {
  return (await parse<{ inferences: Inference[] }>(await fetch('/api/memory/inferences', { cache: 'no-store' }))).inferences;
}

/** 👎 по выводу: он неверный и больше не появится. */
export async function rejectInference(id: string): Promise<void> {
  await parse(await fetch('/api/memory/inferences/' + encodeURIComponent(id) + '/reject', { method: 'POST', headers }));
}
