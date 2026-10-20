import { useEffect, useState } from 'react';
import {
  addMemoryFact, clearHistory, explainMemoryFact, getMemoryCandidates, getMemoryFacts,
  getMemoryPolicy, getMemoryStatus, getMemorySummaries, loadMemory, processMemoryJobs,
  removeMemoryFact, reviewMemoryCandidate, reviewMemorySummary, saveMemory,
  setMemoryPolicy, updateMemoryFact,
} from '../services/chatApi';
import type {
  MemoryCandidate, MemoryFact, MemoryPolicy, MemoryStatus, MemorySummary,
} from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function MemoryEditor({ active }: { active: boolean }) {
  const clearChat = useAppStore(s => s.clearChat);
  const [notes, setNotes] = useState('');
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [summaries, setSummaries] = useState<MemorySummary[]>([]);
  const [policy, setPolicy] = useState<MemoryPolicy | null>(null);
  const [status, setStatus] = useState<MemoryStatus | null>(null);
  const [factDraft, setFactDraft] = useState('');
  const [factCloud, setFactCloud] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function refresh() {
    const [n, f, c, s, p, state] = await Promise.all([
      loadMemory(), getMemoryFacts(), getMemoryCandidates(),
      getMemorySummaries(), getMemoryPolicy(), getMemoryStatus(),
    ]);
    setNotes(n); setFacts(f); setCandidates(c); setSummaries(s); setPolicy(p); setStatus(state);
  }

  useEffect(() => {
    if (!active) return;
    let mounted = true;
    void Promise.all([
      loadMemory(), getMemoryFacts(), getMemoryCandidates(),
      getMemorySummaries(), getMemoryPolicy(), getMemoryStatus(),
    ]).then(([n, f, c, s, p, state]) => {
      if (mounted) {
        setNotes(n); setFacts(f); setCandidates(c);
        setSummaries(s); setPolicy(p); setStatus(state);
      }
    }).catch((cause: unknown) => {
      if (mounted) setError(cause instanceof Error ? cause.message : 'Память недоступна');
    });
    return () => { mounted = false; };
  }, [active]);

  async function action(task: () => Promise<string>) {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await task();
      await refresh();
      setMessage(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось изменить память');
    } finally { setBusy(false); }
  }

  async function updatePolicy(key: keyof MemoryPolicy, value: boolean) {
    if (value && (key === 'allow_cloud_notes' || key === 'allow_cloud_facts')) {
      if (!window.confirm('Разрешить передачу указанной категории памяти в Cloud.ru при включённом облачном чате?')) return;
    }
    await action(async () => {
      await setMemoryPolicy({ [key]: value });
      return 'Разрешения памяти обновлены.';
    });
  }

  async function addFact() {
    if (!factDraft.trim()) return;
    await action(async () => {
      await addMemoryFact(factDraft.trim(), factCloud);
      setFactDraft(''); setFactCloud(false);
      return 'Воспоминание сохранено.';
    });
  }

  async function editFact(fact: MemoryFact) {
    const content = window.prompt('Изменить воспоминание', fact.content);
    if (!content?.trim() || content === fact.content) return;
    await action(async () => {
      await updateMemoryFact(fact, content.trim(), fact.cloudAllowed);
      return 'Воспоминание исправлено.';
    });
  }

  async function toggleFactCloud(fact: MemoryFact) {
    const next = !fact.cloudAllowed;
    if (next && !window.confirm('Разрешить передачу этого факта Cloud.ru?')) return;
    await action(async () => {
      await updateMemoryFact(fact, fact.content, next);
      return next ? 'Факт разрешён для Cloud.ru.' : 'Передача факта запрещена.';
    });
  }

  async function explain(fact: MemoryFact) {
    await action(async () => {
      const result = await explainMemoryFact(fact.id);
      window.alert(result.source
        ? 'Источник: ' + result.source.text
        : 'Источник не указан или исходное сообщение удалено. Тип: ' + fact.kind);
      return 'Информация об источнике открыта.';
    });
  }

  async function forget(fact: MemoryFact) {
    if (!window.confirm('Забыть этот факт? Он будет исключён из поиска и выписок, но исходная переписка сохраняется отдельно.')) return;
    await action(async () => {
      await removeMemoryFact(fact.id);
      return 'Воспоминание удалено из Memory Core.';
    });
  }

  async function review(candidate: MemoryCandidate, approve: boolean) {
    await action(async () => {
      await reviewMemoryCandidate(candidate.id, approve, false);
      return approve ? 'Кандидат подтверждён и сохранён только локально.' : 'Кандидат отклонён.';
    });
  }

  async function reviewSummary(summary: MemorySummary, approve: boolean) {
    await action(async () => {
      await reviewMemorySummary(summary.conversationId, approve, false);
      return approve ? 'Выписка подтверждена. В облако не передаётся.' : 'Выписка отклонена.';
    });
  }

  async function eraseHistory() {
    if (!window.confirm('Удалить историю ОСНОВНОГО диалога вместе с её производной памятью? Другие диалоги и глобальная память останутся.')) return;
    await action(async () => {
      await clearHistory();
      clearChat();
      return 'Основной диалог и связанные воспоминания очищены.';
    });
  }

  return (
    <section className="memory-editor memory-core" aria-label="Управление памятью Meiyuren">
      <h3>Memory Core · умная память</h3>
      <p>SQLite работает локально. Новые факты предлагает автоматический анализ без AI, но сохраняются они только после подтверждения.</p>
      {status && <div className="memory-core__stats">
        <span>Фактов: {status.facts}</span>
        <span>Ожидают: {status.pending}</span>
        <span>Очередь: {status.jobs}</span>
      </div>}
      <button type="button" disabled={busy} onClick={() => void action(async () => {
        const result = await processMemoryJobs();
        return 'Локально обработано задач: ' + result.processed;
      })}>Обработать очередь памяти</button>

      <h4>Разрешения</h4>
      <p>По умолчанию память и заметки не передаются Cloud.ru. История текущего диалога передаётся провайдеру, когда включён облачный чат.</p>
      {policy && ([
        ['allow_cloud_notes', 'Разрешить передачу заметки Cloud.ru'],
        ['allow_cloud_facts', 'Разрешить передачу одобренных фактов Cloud.ru'],
        ['auto_extract', 'Автоматически искать кандидатов (локально)'],
        ['auto_summaries', 'Автоматически создавать выписки (локально)'],
      ] as const).map(([key, caption]) =>
        <label className="memory-core__toggle" key={key}>
          <input type="checkbox" checked={policy[key]} disabled={busy}
            onChange={event => void updatePolicy(key, event.target.checked)} />
          <span>{caption}</span>
        </label>)}

      <h4>Заметка пользователя</h4>
      <textarea aria-label="Заметка памяти" rows={3} maxLength={4000} value={notes}
        disabled={busy} onChange={e => setNotes(e.target.value)} />
      <button type="button" disabled={busy} onClick={() => void action(async () => {
        await saveMemory(notes);
        return 'Заметка сохранена.';
      })}>Сохранить заметку</button>

      <h4>Добавить воспоминание</h4>
      <input aria-label="Новый факт" maxLength={500} value={factDraft} disabled={busy}
        placeholder="Например: я изучаю Python"
        onChange={e => setFactDraft(e.target.value)} />
      <label className="memory-core__toggle">
        <input type="checkbox" disabled={busy} checked={factCloud} onChange={e => {
          if (e.target.checked && !window.confirm('Разрешить этому факту передачу Cloud.ru?')) return;
          setFactCloud(e.target.checked);
        }} />
        <span>Разрешить передачу этого факта Cloud.ru</span>
      </label>
      <button type="button" disabled={busy || !factDraft.trim()} onClick={() => void addFact()}>＋ Запомнить факт</button>

      <h4>Предложения на сохранение ({candidates.length})</h4>
      {candidates.length === 0 && <p>Пока предложений нет.</p>}
      <ul className="memory-core__list">
        {candidates.map(candidate => <li key={candidate.id}>
          <span>{candidate.content}</span>
          <div className="memory-core__actions">
            <button type="button" disabled={busy} onClick={() => void review(candidate, true)}>Запомнить</button>
            <button type="button" disabled={busy} onClick={() => void review(candidate, false)}>Отклонить</button>
          </div>
        </li>)}
      </ul>

      <h4>Сохранённые воспоминания ({facts.length})</h4>
      {facts.length === 0 && <p>Память пока пуста.</p>}
      <ul className="memory-core__list">
        {facts.map(fact => <li key={fact.id}>
          <span>{fact.content}</span>
          <small>{fact.kind === 'legacy' ? 'Из прежней версии — источник не подтверждён' : 'Ревизия ' + fact.revision}
            {fact.cloudAllowed ? ' · Cloud разрешён' : ' · Только локально'}</small>
          <div className="memory-core__actions">
            <button type="button" disabled={busy} onClick={() => void explain(fact)}>Почему?</button>
            <button type="button" disabled={busy} onClick={() => void editFact(fact)}>Изменить</button>
            <button type="button" disabled={busy} onClick={() => void toggleFactCloud(fact)}>{fact.cloudAllowed ? 'Запретить Cloud' : 'Разрешить Cloud'}</button>
            <button type="button" disabled={busy} onClick={() => void forget(fact)}>Забыть</button>
          </div>
        </li>)}
      </ul>

      <h4>Локальные выписки диалогов ({summaries.length})</h4>
      <p>Автоматически формируются из сообщений. Не являются проверенными фактами, пока ты их не подтвердишь.</p>
      <ul className="memory-core__list">
        {summaries.map(summary => <li key={summary.conversationId}>
          <strong>Диалог: {summary.conversationId === 'main' ? 'Основной' : summary.conversationId.slice(0, 8)}</strong>
          <pre>{summary.content}</pre>
          <small>{summary.status === 'draft' ? 'Ожидает подтверждения' : 'Подтверждена · локально'}</small>
          <div className="memory-core__actions">
            {summary.status === 'draft' && <button type="button" disabled={busy}
              onClick={() => void reviewSummary(summary, true)}>Подтвердить</button>}
            <button type="button" disabled={busy}
              onClick={() => void reviewSummary(summary, false)}>Удалить выписку</button>
          </div>
        </li>)}
      </ul>
      <button type="button" disabled={busy} onClick={() => void eraseHistory()}>Очистить основной диалог</button>
      {error && <p className="memory-editor__error" role="alert">{error}</p>}
      {message && <p className="memory-editor__success" role="status">{message}</p>}
    </section>
  );
}
