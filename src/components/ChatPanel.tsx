import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';
import { avatarUrl } from '../lib/avatars';
import {
  createConversation, deleteConversation, describeIdleReport, getConversations, getEngineMode, getIdleBriefing,
  dismissCuriosity, loadHistory, rejectInference, loadOlderHistory, markIdleBriefingSeen, rateRecalledMemory, renameConversation, searchChat, streamMessage, StreamError,
} from '../services/chatApi';
import type { Conversation, ChatMatch, Curiosity, Exchange, IdleBriefing, RecallTrace } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

const BRAIN_LABELS: Record<string, string> = {
  identity: 'личность', episodes: 'события', goals: 'цели', habits: 'привычки',
  knowledge: 'знания', relationships: 'люди', projects: 'проекты', decisions: 'решения',
};

export function ChatPanel() {
  const open = useAppStore(s => s.chatOpen);
  const close = useAppStore(s => s.closeChat);
  const messages = useAppStore(s => s.messages);
  const setMessages = useAppStore(s => s.setMessages);
  const greeting = useAppStore(s => s.greetingEnabled);
  const avatarId = useAppStore(s => s.avatarId);
  const [conversationId, setConversationId] = useState('main');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [draft, setDraft] = useState('');
  const [waiting, setWaiting] = useState(false);
  const [liveText, setLiveText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [search, setSearch] = useState('');
  const [matches, setMatches] = useState<ChatMatch[]>([]);
  const [mode, setMode] = useState<'cloud' | 'demo'>('demo');
  const [hasOlder, setHasOlder] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);
  // Воспоминания, использованные в ответах этой сессии: assistant message id → след.
  const [traces, setTraces] = useState<Record<string, RecallTrace>>({});
  const [questions, setQuestions] = useState<Record<string, Curiosity>>({});
  const [rejected, setRejected] = useState<Record<string, boolean>>({});
  const [rated, setRated] = useState<Record<string, boolean>>({});
  const [briefing, setBriefing] = useState<IdleBriefing | null>(null);
  const controller = useRef<AbortController | null>(null);
  const pending = useRef<{ text: string; conversationId: string; id: string } | null>(null);
  const currentConversation = useRef(conversationId);
  const scroll = useRef<HTMLDivElement>(null);
  currentConversation.current = conversationId;

  useEffect(() => {
    if (!open) return;
    void getConversations().then(setConversations).catch(() => undefined);
    void getEngineMode().then(setMode).catch(() => undefined);
    void getIdleBriefing().then(setBriefing).catch(() => undefined);
  }, [open]);

  function dismissBriefing() {
    setBriefing(null);
    void markIdleBriefingSeen().catch(() => undefined);
  }

  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setLoading(true);
    setError('');
    setMessages([]);
    void loadHistory(conversationId, abort.signal).then(rows => {
      if (!abort.signal.aborted) {
        setMessages(rows);
        setHasOlder(rows.length >= 200);
      }
    }).catch((err: unknown) => {
      if (!abort.signal.aborted) setError(err instanceof Error ? err.message : 'Не удалось загрузить историю');
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [open, conversationId, setMessages]);

  useEffect(() => {
    if (!open || focusId) return;
    scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'smooth' });
  }, [open, messages, liveText, focusId]);

  // Найденное поиском сообщение: догружаем более ранние страницы, прокручиваем и подсвечиваем.
  useEffect(() => {
    if (!open || !focusId || loading) return;
    const node = scroll.current?.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(focusId)}"]`);
    if (node) {
      node.scrollIntoView({ block: 'center', behavior: 'smooth' });
      const timer = window.setTimeout(() => setFocusId(null), 2600);
      return () => window.clearTimeout(timer);
    }
    if (hasOlder) void showOlder();
    else setFocusId(null);
  }, [open, focusId, loading, messages, hasOlder]);

  useEffect(() => () => controller.current?.abort(), []);

  if (!open) return null;

  function switchConversation(id: string, focus: string | null = null) {
    controller.current?.abort();
    controller.current = null;
    setWaiting(false);
    setLiveText('');
    setUncertain(false);
    pending.current = null;
    setMatches([]);
    setSearch('');
    setFocusId(focus);
    setConversationId(id);
  }

  async function showOlder() {
    const first = useAppStore.getState().messages[0];
    if (!first) return;
    try {
      const older = await loadOlderHistory(conversationId, first.id);
      setHasOlder(older.length >= 100);
      if (older.length) setMessages([...older, ...useAppStore.getState().messages]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить ранние сообщения');
    }
  }

  async function manageConversation(action: 'create' | 'rename' | 'delete') {
    setError('');
    try {
      if (action === 'create') {
        const title = window.prompt('Название нового диалога', 'Новый диалог');
        if (!title?.trim()) return;
        const conv = await createConversation(title.trim());
        setConversations(await getConversations());
        switchConversation(conv.id);
      } else if (action === 'rename') {
        const title = window.prompt('Новое название', conversations.find(c => c.id === conversationId)?.title ?? '');
        if (!title?.trim()) return;
        await renameConversation(conversationId, title.trim());
        setConversations(await getConversations());
      } else {
        if (conversationId === 'main') { setError('Основной диалог нельзя удалить.'); return; }
        if (!window.confirm('Удалить диалог, его историю и всё, что память выучила из него?')) return;
        await deleteConversation(conversationId);
        setConversations(await getConversations());
        switchConversation('main');
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось изменить диалог');
    }
  }

  async function findMessages() {
    if (search.trim().length < 2) { setMatches([]); return; }
    try {
      setMatches(await searchChat(search.trim()));
      setError('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка поиска'); }
  }

  function remember(exchange: Exchange) {
    const existing = useAppStore.getState().messages;
    const ids = new Set([exchange.user.id, exchange.assistant.id]);
    setMessages([...existing.filter(item => !ids.has(item.id)), exchange.user, exchange.assistant]);
    if (exchange.memory) {
      const trace = exchange.memory;
      setTraces(value => ({ ...value, [exchange.assistant.id]: trace }));
    }
    if (exchange.curiosity) {
      const question = exchange.curiosity;
      setQuestions(value => ({ ...value, [exchange.assistant.id]: question }));
    }
  }

  async function reject(inferenceId: string) {
    try {
      await rejectInference(inferenceId);
      setRejected(value => ({ ...value, [inferenceId]: true }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось отклонить вывод');
    }
  }

  async function dismiss(messageId: string, question: Curiosity) {
    try {
      await dismissCuriosity(question.id);
      setQuestions(value => {
        const next = { ...value };
        delete next[messageId];
        return next;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось убрать вопрос');
    }
  }

  async function rate(trace: RecallTrace, memoryId: string, helpful: boolean) {
    try {
      await rateRecalledMemory(trace.traceId, memoryId, helpful);
      setRated(value => ({ ...value, [trace.traceId + ':' + memoryId]: helpful }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить оценку');
    }
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || waiting || loading) return;
    const id = pending.current?.text === text && pending.current.conversationId === conversationId
      ? pending.current.id : crypto.randomUUID();
    pending.current = { id, text, conversationId };
    const current = conversationId;
    const abort = new AbortController();
    controller.current = abort;
    setWaiting(true);
    setUncertain(false);
    setLiveText('');
    setError('');
    try {
      const exchange = await streamMessage(text, id, current, part => {
        if (!abort.signal.aborted && currentConversation.current === current) {
          setLiveText(value => value + part);
        }
      }, abort.signal);
      if (!abort.signal.aborted && currentConversation.current === current) {
        remember(exchange);
        pending.current = null;
        setDraft('');
        setLiveText('');
        void getConversations().then(setConversations);
      }
    } catch (cause) {
      if (currentConversation.current !== current) return;
      const streamError = cause instanceof StreamError ? cause : null;
      if (streamError?.saved) {
        // Сервер сохранил реплику и полученную часть ответа: ничего не потеряно.
        remember(streamError.saved);
        pending.current = null;
        setDraft('');
        setLiveText('');
        setError(streamError.message + ' Полученная часть ответа сохранена в истории.');
        return;
      }
      if (abort.signal.aborted) {
        if (mode === 'cloud') {
          setUncertain(true);
          setError('Вывод остановлен. Полученная часть ответа сохранится в истории; повтор с тем же ID не вызовет новую генерацию.');
          window.setTimeout(() => void loadHistory(current).then(rows => {
            if (currentConversation.current === current) setMessages(rows);
          }).catch(() => undefined), 600);
        } else {
          setError('Вывод остановлен.');
        }
        return;
      }
      const paid = streamError ? streamError.paid && streamError.mode !== 'demo' : mode === 'cloud';
      setUncertain(paid);
      if (!paid) pending.current = null;
      setError(cause instanceof Error ? cause.message : 'Ошибка генерации');
    } finally {
      if (controller.current === abort) controller.current = null;
      if (currentConversation.current === current) setWaiting(false);
    }
  }

  function stop() {
    controller.current?.abort();
    setWaiting(false);
  }

  function onComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter отправляет, Shift+Enter переносит строку.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <section className="chat-panel" role="dialog" aria-label="Чат с Мэйюрэн">
      <header className="panel-header">
        <span className="panel-header__mark"><img className="panel-header__portrait" src={avatarUrl(avatarId)} alt="" /></span>
        <div><strong>Мэйюрэн</strong><span className="panel-header__sub">
          {mode === 'cloud' ? 'Cloud.ru · диалоги и память' : 'Локальный режим · диалоги и память'}
        </span></div>
        <button className="icon-button panel-header__close" type="button" aria-label="Закрыть чат" onClick={() => { controller.current?.abort(); close(); }}>×</button>
      </header>
      <div className="chat-v06__tools">
        <select aria-label="Выбор диалога" value={conversationId} onChange={e => switchConversation(e.target.value)}>
          {conversations.length === 0 && <option value="main">Основной диалог</option>}
          {conversations.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
        <button type="button" title="Новый диалог" aria-label="Новый диалог" onClick={() => void manageConversation('create')}>＋</button>
        <button type="button" title="Переименовать диалог" aria-label="Переименовать диалог" onClick={() => void manageConversation('rename')}>✎</button>
        <button type="button" title="Удалить диалог" aria-label="Удалить диалог" disabled={conversationId === 'main'} onClick={() => void manageConversation('delete')}>×</button>
      </div>
      <div className="chat-v06__search">
        <input aria-label="Поиск по сообщениям" placeholder="Поиск по истории…" value={search} maxLength={100}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') void findMessages(); }} />
        <button type="button" onClick={() => void findMessages()} disabled={search.trim().length < 2}>Найти</button>
      </div>
      {matches.length > 0 && <div className="chat-v06__results">
        <button type="button" onClick={() => setMatches([])}>Закрыть результаты ×</button>
        {matches.map(m => <button type="button" key={m.id} onClick={() => {
          if (m.conversationId === conversationId) { setMatches([]); setFocusId(m.id); }
          else switchConversation(m.conversationId, m.id);
        }}>
          {m.role === 'user' ? 'Вы' : 'Мэйюрэн'}: {m.text.slice(0, 100)}
        </button>)}
      </div>}
      {briefing && <IdleCard briefing={briefing} onClose={dismissBriefing} />}
      <div className="chat-panel__messages" ref={scroll} aria-live="polite" aria-relevant="additions text">
        {loading && <div className="chat-panel__empty">Загружаю историю…</div>}
        {!loading && hasOlder && <button type="button" className="chat-panel__older" onClick={() => void showOlder()}>
          Показать более ранние сообщения
        </button>}
        {!loading && messages.length === 0 && <div className="chat-panel__empty">
          {greeting ? 'Привет! Я Мэйюрэн ✨ Напиши мне сообщение.' : 'В этом диалоге пока нет сообщений.'}
        </div>}
        {!loading && messages.map(item => {
          const trace = item.role === 'assistant' ? traces[item.id] : undefined;
          const question = item.role === 'assistant' ? questions[item.id] : undefined;
          return <div className={`message message--${item.role}${focusId === item.id ? ' message--focus' : ''}`}
            key={item.id} data-message-id={item.id}>
            <div className="message__text">{item.text}</div>
            {trace && (trace.items.length > 0 || (trace.inferences ?? []).length > 0) && <details className="message__memory">
              <summary>Память: {trace.items.length}{(trace.inferences ?? []).length > 0 ? ' · выводы: ' + (trace.inferences ?? []).length : ''}</summary>
              <ul>
                {trace.items.map(memory => {
                  const verdict = rated[trace.traceId + ':' + memory.id];
                  return <li key={memory.id}>
                    <span>{memory.content}</span>
                    <small>{BRAIN_LABELS[memory.brain] ?? memory.brain}</small>
                    <button type="button" aria-label="Полезно" title="Полезно: учит память и эволюцию"
                      aria-pressed={verdict === true} onClick={() => void rate(trace, memory.id, true)}>👍</button>
                    <button type="button" aria-label="Не к месту" title="Не к месту"
                      aria-pressed={verdict === false} onClick={() => void rate(trace, memory.id, false)}>👎</button>
                  </li>;
                })}
                {(trace.inferences ?? []).filter(inference => !rejected[inference.id]).map(inference => <li key={inference.id}
                  className="message__inference">
                  <span>Вывод: {inference.content}
                    <small> · потому что {inference.because.map(item => '«' + item.content + '»').join(' + ')}</small></span>
                  <button type="button" aria-label="Неверный вывод" title="Неверный вывод: больше не появится"
                    onClick={() => void reject(inference.id)}>👎</button>
                </li>)}
              </ul>
            </details>}
            {question && <div className="message__curiosity">
              <span>🤔 {question.question}</span>
              <button type="button" onClick={() => void dismiss(item.id, question)}>Не спрашивать об этом</button>
            </div>}
            <span className="message__time">{new Date(item.sentAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>;
        })}
        {(waiting || (uncertain && liveText)) && <div className="message message--assistant"><div className="message__text">{liveText || 'Мэйюрэн печатает…'}{uncertain && !waiting ? '\n\n[Частичный ответ]' : ''}</div></div>}
      </div>
      {error && <p role="alert" className="chat-panel__error">{error}</p>}
      {uncertain && !waiting && mode === 'cloud' && <button type="button" className="chat-panel__new-request" onClick={() => {
        if (window.confirm('Отправить НОВЫЙ запрос? Предыдущий мог быть обработан и оплачен Cloud.ru.')) {
          pending.current = null;
          setUncertain(false);
          setError('Можно отправить новый запрос. Возможна повторная оплата.');
        }
      }}>Создать новый запрос (возможна повторная оплата)</button>}
      <form className="chat-panel__composer" onSubmit={event => { void submit(event); }}>
        <textarea aria-label="Сообщение" placeholder="Напиши Мэйюрэн…" title="Enter — отправить, Shift+Enter — новая строка" maxLength={2000}
          rows={Math.min(5, Math.max(1, draft.split('\n').length))}
          value={draft} disabled={waiting || loading} onKeyDown={onComposerKey} onChange={event => {
            setDraft(event.target.value);
            if (pending.current?.text !== event.target.value.trim()) { pending.current = null; setUncertain(false); }
          }} />
        {waiting
          ? <button type="button" aria-label="Остановить ответ" title="Остановить ответ" onClick={stop}>■</button>
          : <button type="submit" aria-label="Отправить сообщение" disabled={!draft.trim() || loading}>➤</button>}
      </form>
      <div className="chat-panel__footnote">
        {mode === 'cloud'
          ? 'История хранится в SQLite. В облачный режим передаются только разрешённые воспоминания.'
          : 'История и память хранятся только на этом компьютере.'}
      </div>
    </section>
  );
}

function IdleCard({ briefing, onClose }: { briefing: IdleBriefing; onClose: () => void }) {
  const lines = describeIdleReport(briefing.report);
  const unfinished = briefing.report.unfinished?.items ?? [];
  return <aside className="chat-idle" aria-label="Пока тебя не было">
    <div className="chat-idle__head">
      <strong>Пока тебя не было</strong>
      <button type="button" aria-label="Скрыть отчёт" onClick={onClose}>×</button>
    </div>
    {lines.length > 0 && <ul>{lines.map(line => <li key={line}>{line}</li>)}</ul>}
    {unfinished.length > 0 && <>
      <div className="chat-idle__sub">Можем продолжить:</div>
      <ul>{unfinished.map(item => <li key={item}>{item}</li>)}</ul>
    </>}
    {briefing.interrupted && <div className="chat-idle__sub">Работу прервало твоё сообщение, остальное доделаю в следующий раз.</div>}
    <div className="chat-idle__note">Всё сделано локально, без Cloud.ru и без затрат.</div>
  </aside>;
}
