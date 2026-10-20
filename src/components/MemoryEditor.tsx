import { useEffect, useState } from 'react';
import {
  addMemoryFact, changeMemoryPolicy, clearHistory, editMemoryFact, explainMemoryFact,
  getMemoryCandidates, getMemoryFacts, getMemoryStatus, getMemorySummaries,
  loadMemory, processMemory, removeMemoryFact, reviewMemoryCandidate,
  reviewMemorySummary, saveMemory,
} from '../services/chatApi';
import type { MemoryCandidate, MemoryExplanation, MemoryFact, MemoryPolicy, MemoryStatus, MemorySummary } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function MemoryEditor({ active }: { active: boolean }) {
  const clearChat = useAppStore(s => s.clearChat);
  const [notes, setNotes] = useState('');
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [summaries, setSummaries] = useState<MemorySummary[]>([]);
  const [status, setStatus] = useState<MemoryStatus | null>(null);
  const [factDraft, setFactDraft] = useState('');
  const [explanation, setExplanation] = useState<MemoryExplanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    const [loadedFacts, loadedCandidates, loadedSummaries, loadedStatus] = await Promise.all([
      getMemoryFacts(), getMemoryCandidates(), getMemorySummaries(), getMemoryStatus(),
    ]);
    setFacts(loadedFacts);
    setCandidates(loadedCandidates);
    setSummaries(loadedSummaries);
    setStatus(loadedStatus);
  }

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void Promise.all([loadMemory(), getMemoryFacts(), getMemoryCandidates(), getMemorySummaries(), getMemoryStatus()])
      .then(([text, items, pending, briefs, state]) => {
        if (cancelled) return;
        setNotes(text); setFacts(items); setCandidates(pending); setSummaries(briefs); setStatus(state);
        setError('');
      }).catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Не удалось загрузить память');
      });
    return () => { cancelled = true; };
  }, [active]);

  async function run(work: () => Promise<void>, success: string) {
    setBusy(true); setError(''); setMessage('');
    try {
      await work();
      await refresh();
      setMessage(success);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Операция памяти не выполнена');
    } finally { setBusy(false); }
  }

  function updatePolicy(key: keyof MemoryPolicy, value: boolean) {
    void run(async () => {
      const updated = await changeMemoryPolicy({ [key]: value });
      setStatus(current => current ? { ...current, policy: updated } : null);
    }, 'Разрешения памяти обновлены.');
  }

  function reviewCandidate(candidate: MemoryCandidate, approve: boolean) {
    void run(() => reviewMemoryCandidate(candidate.id, approve), approve
      ? 'Воспоминание подтверждено и сохранено локально. Облачная передача выключена.'
      : 'Предложение отклонено.');
  }

  function reviewSummary(summary: MemorySummary, approve: boolean) {
    void run(() => reviewMemorySummary(summary.conversationId, approve), approve
      ? 'Локальная выписка подтверждена. В Cloud.ru не отправляется.'
      : 'Выписка отклонена.');
  }

  function editFact(item: MemoryFact) {
    const content = window.prompt('Исправить воспоминание', item.content);
    if (content === null || !content.trim()) return;
    void run(async () => {
      await editMemoryFact(item, { content: content.trim(), cloudAllowed: item.cloudAllowed, expiresAt: item.expiresAt });
    }, 'Воспоминание исправлено, ревизия сохранена.');
  }

  function toggleFactCloud(item: MemoryFact) {
    if (!item.cloudAllowed && !window.confirm('Разрешить передавать это воспоминание Cloud.ru? Для передачи также должен быть включён общий переключатель.')) return;
    void run(async () => {
      await editMemoryFact(item, { content: item.content, cloudAllowed: !item.cloudAllowed, expiresAt: item.expiresAt });
    }, 'Права передачи обновлены.');
  }

  function forget(item: MemoryFact) {
    if (!window.confirm('Удалить воспоминание, его ревизии и индекс? Исходное сообщение в истории удаляется отдельно.')) return;
    void run(async () => {
      await removeMemoryFact(item.id);
      if (explanation?.item.id === item.id) setExplanation(null);
    }, 'Воспоминание и производный поисковый индекс удалены.');
  }

  async function explain(item: MemoryFact) {
    setError('');
    try { setExplanation(await explainMemoryFact(item.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось открыть источник'); }
  }

  if (!active) return null;
  const policy = status?.policy;
  return (
    <section className="memory-editor memory-core" aria-label="Единая память Мэйюрэн">
      <h3>Memory Core · память Мэйюрэн</h3>
      <p>Один локальный модуль: поиск, кандидаты, выписки, ревизии и забывание. Анализ выполняется на ноутбуке без дополнительных платных запросов.</p>
      {status && <p className="memory-core__statistics">
        {status.facts} фактов · {status.pending} на подтверждении · {status.summaries} выписок · {status.jobs} задач
      </p>}
      {policy && <fieldset className="memory-core__policy" disabled={busy}>
        <legend>Правила памяти</legend>
        <label><input type="checkbox" checked={policy.auto_extract} onChange={e => updatePolicy('auto_extract', e.target.checked)} />
          Автоматически искать кандидатов в сообщениях</label>
        <label><input type="checkbox" checked={policy.auto_summaries} onChange={e => updatePolicy('auto_summaries', e.target.checked)} />
          Создавать локальные выписки длинных диалогов</label>
        <label><input type="checkbox" checked={policy.allow_cloud_facts} onChange={e => updatePolicy('allow_cloud_facts', e.target.checked)} />
          Разрешить Cloud.ru только отдельно отмеченные факты</label>
        <label><input type="checkbox" checked={policy.allow_cloud_notes} onChange={e => updatePolicy('allow_cloud_notes', e.target.checked)} />
          Разрешить передачу общей заметки Cloud.ru</label>
      </fieldset>}
      <p>Даже при разрешённой памяти текст текущего сообщения и история чата отдельно передаются Cloud.ru в облачном режиме.</p>

      <label htmlFor="meiyuren-memory-notes">Общая заметка (только локально, пока не разрешена передача)</label>
      <textarea id="meiyuren-memory-notes" rows={3} maxLength={4000} value={notes} disabled={busy}
        onChange={e => setNotes(e.target.value)} placeholder="Что Мэйюрэн должна помнить?" />
      <div className="memory-editor__actions">
        <button type="button" disabled={busy} onClick={() => void run(() => saveMemory(notes), 'Заметка сохранена в SQLite.')}>
          Сохранить заметку
        </button>
        <button type="button" disabled={busy} onClick={() => void run(async () => {
          const processed = await processMemory();
          setStatus(processed);
        }, 'Локальные задания обработаны.')}>Обработать очередь</button>
      </div>

      <h3>Добавить подтверждённый факт</h3>
      <input aria-label="Новый факт памяти" value={factDraft} maxLength={500} disabled={busy}
        placeholder="Например: предпочитаю короткие ответы"
        onChange={e => setFactDraft(e.target.value)} />
      <button type="button" disabled={busy || !factDraft.trim()} onClick={() => void run(async () => {
        await addMemoryFact(factDraft.trim());
        setFactDraft('');
      }, 'Факт сохранён локально.')}>＋ Запомнить</button>

      <h3>Предложения на подтверждение ({candidates.length})</h3>
      {candidates.length === 0 && <p>Нет новых предложений. Система не сохраняет догадки автоматически.</p>}
      <ul className="memory-core__list">
        {candidates.map(candidate => <li key={candidate.id}>
          <span>{candidate.content}<small>Источник: сообщение пользователя</small></span>
          <div>
            <button type="button" disabled={busy} onClick={() => reviewCandidate(candidate, true)}>Подтвердить</button>
            <button type="button" disabled={busy} onClick={() => reviewCandidate(candidate, false)}>Отклонить</button>
          </div>
        </li>)}
      </ul>

      <h3>Подтверждённая память ({facts.length})</h3>
      {facts.length === 0 && <p>Нет сохранённых фактов.</p>}
      <ul className="memory-core__list">
        {facts.map(item => <li key={item.id}>
          <span>{item.content}
            <small>{item.kind === 'legacy' ? 'Импортировано из старой памяти · источник неизвестен'
              : item.kind === 'extracted' ? 'Подтверждено из переписки' : 'Добавлено вручную'} · ревизия {item.revision}</small>
          </span>
          <div>
            <button type="button" disabled={busy} onClick={() => void explain(item)}>Почему?</button>
            <button type="button" disabled={busy} onClick={() => editFact(item)}>Изменить</button>
            <button type="button" disabled={busy} onClick={() => toggleFactCloud(item)}>
              {item.cloudAllowed ? 'Cloud.ru: да' : 'Cloud.ru: нет'}
            </button>
            <button type="button" disabled={busy} onClick={() => forget(item)}>Удалить</button>
          </div>
        </li>)}
      </ul>
      {explanation && <div className="memory-core__explanation">
        <strong>Почему Мэйюрэн это помнит?</strong>
        <p>{explanation.item.content}</p>
        <p>Источник: {explanation.source?.text ?? 'Недоступен или добавлено вручную'}</p>
        <p>Ревизий: {explanation.revisions.length}; версия: {explanation.item.revision}</p>
        {explanation.revisions.map(rev => <p key={rev.revision}>Версия {rev.revision}: {rev.content}</p>)}
        <button type="button" onClick={() => setExplanation(null)}>Закрыть</button>
      </div>}

      <h3>Локальные выписки диалогов</h3>
      {summaries.length === 0 && <p>После достаточно длинного разговора появится выписка на проверку.</p>}
      <ul className="memory-core__list">
        {summaries.map(summary => <li key={summary.conversationId}>
          <span className="memory-core__summary">{summary.content}<small>Статус: {summary.status}</small></span>
          {summary.status === 'draft' && <div>
            <button type="button" disabled={busy} onClick={() => reviewSummary(summary, true)}>Подтвердить</button>
            <button type="button" disabled={busy} onClick={() => reviewSummary(summary, false)}>Отклонить</button>
          </div>}
        </li>)}
      </ul>

      <div className="memory-editor__actions">
        <button type="button" disabled={busy} onClick={() => {
          if (!window.confirm('Удалить всю историю ОСНОВНОГО диалога и связанные с ней извлечённые факты? Другие диалоги останутся.')) return;
          void run(async () => { await clearHistory(); clearChat(); }, 'История основного диалога очищена.');
        }}>Очистить основной диалог</button>
      </div>
      {error && <p className="memory-editor__error" role="alert">{error}</p>}
      {message && <p className="memory-editor__success" role="status">{message}</p>}
    </section>
  );
}
