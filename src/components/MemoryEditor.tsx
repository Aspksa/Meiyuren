import { useEffect, useState } from 'react';
import {
  addMemoryFact, clearHistory, explainMemoryFact, getMemoryCandidates, getMemoryFacts,
  getMemoryPolicy, getMemoryStatus, getMemorySummaries, loadMemory, processMemoryJobs,
  removeMemoryFact, reviewMemoryCandidate, reviewMemorySummary, saveMemory,
  setMemoryPolicy, updateMemoryFact, previewMemoryRecall, getMemoryUsage,
  getMemoryBrainLinks, indexMemoryNeural, searchMemoryNeural, clearMemoryNeuralVectors,
} from '../services/chatApi';
import type {
  MemoryCandidate, MemoryExplanation, MemoryFact, MemoryPolicy, MemoryRecallPreview,
  MemoryStatus, MemorySummary, MemoryUsage, MemoryBrain, MemoryConnection, MemoryNeuralMatch,
} from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

const BRAIN_NAMES: Record<MemoryBrain, string> = {
  identity: 'Личность', episodes: 'События', goals: 'Цели',
  habits: 'Привычки', knowledge: 'Знания',
};

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
  const [brainDraft, setBrainDraft] = useState<MemoryBrain | ''>('');
  const [connections, setConnections] = useState<MemoryConnection[]>([]);
  const [connectedSource, setConnectedSource] = useState('');
  const [neuralQuery, setNeuralQuery] = useState('');
  const [neuralMatches, setNeuralMatches] = useState<MemoryNeuralMatch[] | null>(null);
  const [explanation, setExplanation] = useState<MemoryExplanation | null>(null);
  const [recallQuery, setRecallQuery] = useState('');
  const [recallCloud, setRecallCloud] = useState(true);
  const [recallResult, setRecallResult] = useState<MemoryRecallPreview | null>(null);
  const [usage, setUsage] = useState<MemoryUsage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function refresh() {
    const [n, f, c, s, p, state, logs] = await Promise.all([
      loadMemory(), getMemoryFacts(), getMemoryCandidates(),
      getMemorySummaries(), getMemoryPolicy(), getMemoryStatus(), getMemoryUsage(),
    ]);
    setNotes(n); setFacts(f); setCandidates(c); setSummaries(s); setPolicy(p); setStatus(state); setUsage(logs);
  }

  useEffect(() => {
    if (!active) return;
    let mounted = true;
    void Promise.all([
      loadMemory(), getMemoryFacts(), getMemoryCandidates(),
      getMemorySummaries(), getMemoryPolicy(), getMemoryStatus(), getMemoryUsage(),
    ]).then(([n, f, c, s, p, state, logs]) => {
      if (mounted) {
        setNotes(n); setFacts(f); setCandidates(c);
        setSummaries(s); setPolicy(p); setStatus(state); setUsage(logs);
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
    if (value && key === 'allow_cloud_embeddings') {
      if (!window.confirm('Разрешить отдельные ручные платные запросы к embedding-модели Cloud.ru? Самостоятельный фоновый запуск запрещён.')) return;
    } else if (value && (key === 'allow_cloud_notes' || key === 'allow_cloud_facts')) {
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
      await addMemoryFact(factDraft.trim(), factCloud, brainDraft || null);
      setFactDraft(''); setFactCloud(false); setBrainDraft('');
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
      setExplanation(result);
      return 'Источник и ревизии показаны ниже.';
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
    if (approve && candidate.conflictWith && !window.confirm(
      'Обнаружено противоположное предпочтение. Подтверждение пометит прежнее воспоминание устаревшим. Продолжить?',
    )) return;
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

  async function setExpiry(fact: MemoryFact) {
    const current = fact.expiresAt ? new Date(fact.expiresAt).toISOString().slice(0, 10) : '';
    const input = window.prompt('Срок актуальности YYYY-MM-DD (пусто — бессрочно)', current);
    if (input === null) return;
    const cleaned = input.trim();
    const date = cleaned ? Date.parse(cleaned + 'T23:59:59Z') : null;
    if (cleaned && (!/^\d{4}-\d{2}-\d{2}$/.test(cleaned) || date === null || !Number.isFinite(date))) {
      setError('Используй дату в формате YYYY-MM-DD.');
      return;
    }
    await action(async () => {
      await updateMemoryFact(fact, fact.content, fact.cloudAllowed, date);
      return 'Срок актуальности изменён.';
    });
  }

  async function runPreview() {
    if (recallQuery.trim().length < 2) return;
    await action(async () => {
      const result = await previewMemoryRecall(recallQuery.trim(), 'main', recallCloud);
      setRecallResult(result);
      return 'Предпросмотр выполнен без платного запроса Cloud.ru.';
    });
  }

  async function setBrain(fact: MemoryFact, brain: MemoryBrain) {
    await action(async () => {
      await updateMemoryFact(fact, fact.content, fact.cloudAllowed, fact.expiresAt, brain);
      return 'Область долгосрочной памяти обновлена.';
    });
  }

  async function showLinks(fact: MemoryFact) {
    await action(async () => {
      const found = await getMemoryBrainLinks(fact.id);
      setConnectedSource(fact.content);
      setConnections(found);
      return 'Найдено связанных воспоминаний: ' + found.length;
    });
  }

  async function indexNeural(fact: MemoryFact) {
    if (!window.confirm('Создать нейровектор этого факта через Cloud.ru? Текст будет передан провайдеру; операция может быть платной.')) return;
    await action(async () => {
      const result = await indexMemoryNeural(fact.id, crypto.randomUUID());
      return result.cached ? 'Нейровектор уже сохранён.' : 'Нейровектор сохранён в SQLite.';
    });
  }

  async function neuralSearch() {
    if (neuralQuery.trim().length < 2) return;
    if (!window.confirm('Отправить поисковый вопрос embedding-модели Cloud.ru? Это может быть платным запросом.')) return;
    await action(async () => {
      const matches = await searchMemoryNeural(neuralQuery.trim(), crypto.randomUUID());
      setNeuralMatches(matches);
      return 'Нейросетевой поиск выполнен.';
    });
  }

  async function deleteNeural() {
    if (!window.confirm('Удалить все локальные нейровекторы и нейросетевые связи? Обычные воспоминания сохранятся.')) return;
    await action(async () => {
      const count = await clearMemoryNeuralVectors();
      setNeuralMatches(null);
      return 'Удалено нейровекторов: ' + count;
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
      {status && <>
        <div className="memory-core__stats">
          <span>Фактов: {status.facts}</span>
          <span>Ожидают: {status.pending}</span>
          <span>Очередь: {status.jobs}</span>
          <span>Связей: {status.network.links}</span>
          <span>Нейровекторов: {status.network.neuralVectors}</span>
        </div>
        <h4>Пять связанных мозгов долгосрочной памяти</h4>
        <div className="memory-core__brains">
          {(Object.keys(BRAIN_NAMES) as MemoryBrain[]).map(key => <div key={key}>
            <strong>{BRAIN_NAMES[key]}</strong>
            <span>{status.network.brains[key] ?? 0}</span>
          </div>)}
        </div>
      </>}
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
        ['allow_cloud_embeddings', 'Разрешить ручную нейроиндексацию через Cloud.ru (может быть платной)'],
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
        <span>Мозг для нового воспоминания</span>
        <select aria-label="Область нового воспоминания" value={brainDraft}
          disabled={busy} onChange={event => setBrainDraft(event.target.value as MemoryBrain | '')}>
          <option value="">Автоматически по тексту</option>
          {(Object.keys(BRAIN_NAMES) as MemoryBrain[]).map(key =>
            <option key={key} value={key}>{BRAIN_NAMES[key]}</option>)}
        </select>
      </label>
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
          <small>Предложенная область: {BRAIN_NAMES[candidate.brain]}</small>
          {candidate.conflictWith && <small>⚠ Возможное противоречие с сохранённым фактом</small>}
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
          <small>Мозг: {BRAIN_NAMES[fact.brain]} · {fact.kind === 'legacy' ? 'Из прежней версии — источник не подтверждён' : 'Ревизия ' + fact.revision}
            {fact.cloudAllowed ? ' · Cloud разрешён' : ' · Только локально'}</small>
          <label className="memory-core__toggle">
            <span>Тип памяти</span>
            <select aria-label={'Мозг воспоминания ' + fact.content} disabled={busy}
              value={fact.brain} onChange={event => void setBrain(fact, event.target.value as MemoryBrain)}>
              {(Object.keys(BRAIN_NAMES) as MemoryBrain[]).map(key =>
                <option key={key} value={key}>{BRAIN_NAMES[key]}</option>)}
            </select>
          </label>
          <div className="memory-core__actions">
            <button type="button" disabled={busy} onClick={() => void explain(fact)}>Почему?</button>
            <button type="button" disabled={busy} onClick={() => void showLinks(fact)}>Нейросвязи</button>
            {policy?.allow_cloud_embeddings && fact.cloudAllowed && <button type="button"
              disabled={busy} onClick={() => void indexNeural(fact)}>Создать нейровектор</button>}
            <button type="button" disabled={busy} onClick={() => void editFact(fact)}>Изменить</button>
            <button type="button" disabled={busy} onClick={() => void setExpiry(fact)}>Срок</button>
            <button type="button" disabled={busy} onClick={() => void toggleFactCloud(fact)}>{fact.cloudAllowed ? 'Запретить Cloud' : 'Разрешить Cloud'}</button>
            <button type="button" disabled={busy} onClick={() => void forget(fact)}>Забыть</button>
          </div>
        </li>)}
      </ul>

      {connectedSource && <section className="memory-core__explanation">
        <h4>Связи пяти мозгов</h4>
        <p>Исходное воспоминание: {connectedSource}</p>
        {connections.length === 0 && <p>Пока нет связанных воспоминаний.</p>}
        <ul className="memory-core__list">
          {connections.map(edge => <li key={edge.item.id + edge.relation}>
            {BRAIN_NAMES[edge.item.brain]} · {edge.item.content}
            <small>{edge.relation === 'neural_similarity' ? 'Нейросетевая близость' : 'Общая тема'} · {Math.round(edge.weight * 100)}%</small>
          </li>)}
        </ul>
        <button type="button" onClick={() => { setConnectedSource(''); setConnections([]); }}>Закрыть связи</button>
      </section>}

      {explanation && <section className="memory-core__explanation" aria-label="Происхождение воспоминания">
        <h4>Почему Мэйюрэн это помнит?</h4>
        <p>{explanation.item.content}</p>
        <small>Источник: {explanation.source?.text ?? 'Удалён или неизвестен'}</small>
        <h4>История правок</h4>
        <ul className="memory-core__list">
          {explanation.revisions.map(entry => <li key={entry.revision}>
            Версия {entry.revision} · {entry.action}: {entry.content}
          </li>)}
        </ul>
        <button type="button" onClick={() => setExplanation(null)}>Закрыть</button>
      </section>}

      <h4>Семантический нейропоиск Cloud.ru</h4>
      <p>Только вручную после подтверждения платного вызова. Поиск идёт по ранее созданным нейровекторам разрешённых фактов.</p>
      <input aria-label="Вопрос нейропоиска" maxLength={200} value={neuralQuery}
        placeholder="Найти воспоминание по смыслу" onChange={e => setNeuralQuery(e.target.value)} />
      <div className="memory-core__actions">
        <button type="button" disabled={busy || !policy?.allow_cloud_embeddings || neuralQuery.trim().length < 2}
          onClick={() => void neuralSearch()}>Нейропоиск (Cloud.ru)</button>
        <button type="button" disabled={busy} onClick={() => void deleteNeural()}>Удалить нейровекторы</button>
      </div>
      {neuralMatches && <ul className="memory-core__list">
        {neuralMatches.length === 0 && <li>Подходящих нейровекторов не найдено.</li>}
        {neuralMatches.map(match => <li key={match.item.id}>
          {BRAIN_NAMES[match.item.brain]} · {match.item.content}
          <small>Сходство: {Math.round(match.similarity * 100)}%</small>
        </li>)}
      </ul>}
      <h4>Какую память Мэйюрэн использует?</h4>
      <p>Предпросмотр выбора фактов. Он ничего не отправляет в Cloud.ru.</p>
      <input aria-label="Проверочный вопрос памяти" maxLength={200}
        placeholder="Например: какие игры я люблю?" value={recallQuery}
        onChange={event => setRecallQuery(event.target.value)} />
      <label className="memory-core__toggle">
        <input type="checkbox" checked={recallCloud} onChange={e => setRecallCloud(e.target.checked)} />
        <span>Проверить правила передачи в Cloud.ru</span>
      </label>
      <button type="button" disabled={busy || recallQuery.trim().length < 2}
        onClick={() => void runPreview()}>Предпросмотр памяти</button>
      {recallResult && <div className="memory-core__explanation">
        <strong>Найдено воспоминаний: {recallResult.memories.length}</strong>
        <pre>{recallResult.context || 'Разрешённого контекста для этого вопроса нет.'}</pre>
      </div>}
      <h4>Журнал выбора памяти ({usage.length})</h4>
      <p>Показывает локальный выбор фактов при подготовке контекста, не подтверждает получение ответа Cloud.ru.</p>
      <ul className="memory-core__list">
        {usage.slice(0, 10).map((entry, i) => <li key={entry.memoryId + ':' + entry.selectedAt + ':' + i}>
          {new Date(entry.selectedAt).toLocaleString('ru-RU')} ·
          {entry.cloudMode ? ' Cloud.ru' : ' локально'} · {entry.content}
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
