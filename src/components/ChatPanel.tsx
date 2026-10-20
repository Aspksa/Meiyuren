import { FormEvent, useEffect, useRef, useState } from 'react';
import { avatarUrl } from '../lib/avatars';
import { startingPosition } from '../lib/position';
import {
  createConversation, deleteConversation, getConversations, loadHistory,
  renameConversation, searchChat, streamMessage,
} from '../services/chatApi';
import type { Conversation, ChatMatch } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function ChatPanel() {
  const open = useAppStore(s => s.chatOpen);
  const close = useAppStore(s => s.closeChat);
  const messages = useAppStore(s => s.messages);
  const setMessages = useAppStore(s => s.setMessages);
  const greeting = useAppStore(s => s.greetingEnabled);
  const position = useAppStore(s => s.position);
  const size = useAppStore(s => s.size);
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
  const controller = useRef<AbortController | null>(null);
  const pending = useRef<{ text: string; conversationId: string; id: string } | null>(null);
  const currentConversation = useRef(conversationId);
  const scroll = useRef<HTMLDivElement>(null);
  currentConversation.current = conversationId;

  useEffect(() => {
    if (!open) return;
    const signal = new AbortController();
    void getConversations().then(setConversations).catch(() => undefined);
    return () => signal.abort();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setLoading(true);
    setError('');
    setMessages([]);
    void loadHistory(conversationId, abort.signal).then(rows => {
      if (!abort.signal.aborted) setMessages(rows);
    }).catch((err: unknown) => {
      if (!abort.signal.aborted) setError(err instanceof Error ? err.message : 'Не удалось загрузить историю');
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [open, conversationId, setMessages]);

  useEffect(() => {
    if (!open) return;
    scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'smooth' });
  }, [open, messages, liveText]);

  useEffect(() => () => controller.current?.abort(), []);

  if (!open) return null;
  const avatarX = (position ?? startingPosition(size, window.innerWidth, window.innerHeight)).x;
  const side = avatarX + size / 2 > window.innerWidth / 2 ? 'left' : 'right';

  function switchConversation(id: string) {
    controller.current?.abort();
    controller.current = null;
    setWaiting(false);
    setLiveText('');
    setUncertain(false);
    pending.current = null;
    setMatches([]);
    setSearch('');
    setConversationId(id);
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
        if (!window.confirm('Удалить диалог и всю его историю без возможности восстановления?')) return;
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
        const existing = useAppStore.getState().messages;
        const ids = new Set([exchange.user.id, exchange.assistant.id]);
        setMessages([...existing.filter(item => !ids.has(item.id)), exchange.user, exchange.assistant]);
        pending.current = null;
        setDraft('');
        setLiveText('');
        void getConversations().then(setConversations);
      }
    } catch (cause) {
      if (currentConversation.current === current) {
        setUncertain(true);
        setError(abort.signal.aborted
          ? 'Вывод остановлен. Cloud.ru мог уже выполнить запрос; повтор с тем же ID не вызовет новую генерацию.'
          : cause instanceof Error ? cause.message : 'Ошибка генерации');
      }
    } finally {
      if (controller.current === abort) controller.current = null;
      if (currentConversation.current === current) setWaiting(false);
    }
  }

  function stop() {
    controller.current?.abort();
    setWaiting(false);
    setUncertain(true);
    setError('Поток остановлен. Уже обработанные токены могли быть оплачены. Повтор заблокирован идентификатором запроса.');
  }

  return (
    <section className={`chat-panel chat-panel--${side}`} role="dialog" aria-label="Чат с Мэйюрэн">
      <header className="panel-header">
        <span className="panel-header__mark"><img className="panel-header__portrait" src={avatarUrl(avatarId)} alt="" /></span>
        <div><strong>Мэйюрэн</strong><span className="panel-header__sub">Cloud.ru · диалоги и память</span></div>
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
        {matches.map(m => <button type="button" key={m.id} onClick={() => switchConversation(m.conversationId)}>
          {m.role === 'user' ? 'Вы' : 'Мэйюрэн'}: {m.text.slice(0, 100)}
        </button>)}
      </div>}
      <div className="chat-panel__messages" ref={scroll} aria-live="polite" aria-relevant="additions text">
        {loading && <div className="chat-panel__empty">Загружаю историю…</div>}
        {!loading && messages.length === 0 && <div className="chat-panel__empty">
          {greeting ? 'Привет! Я Мэйюрэн ✨ Напиши мне сообщение.' : 'В этом диалоге пока нет сообщений.'}
        </div>}
        {!loading && messages.map(item => <div className={`message message--${item.role}`} key={item.id}>
          <div className="message__text">{item.text}</div>
          <span className="message__time">{new Date(item.sentAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>)}
        {(waiting || (uncertain && liveText)) && <div className="message message--assistant"><div className="message__text">{liveText || 'Мэйюрэн печатает…'}{uncertain && !waiting ? '\n\n[Частичный ответ, не сохранён в истории]' : ''}</div></div>}
      </div>
      {error && <p role="alert" className="chat-panel__error">{error}</p>}
      {uncertain && !waiting && <button type="button" className="chat-panel__new-request" onClick={() => {
        if (window.confirm('Отправить НОВЫЙ запрос? Предыдущий мог быть обработан и оплачен Cloud.ru.')) {
          pending.current = null;
          setUncertain(false);
          setError('Можно отправить новый запрос. Возможна повторная оплата.');
        }
      }}>Создать новый запрос (возможна повторная оплата)</button>}
      <form className="chat-panel__composer" onSubmit={event => { void submit(event); }}>
        <input aria-label="Сообщение" placeholder="Напиши Мэйюрэн…" maxLength={2000}
          value={draft} disabled={waiting || loading} onChange={event => {
            setDraft(event.target.value);
            if (pending.current?.text !== event.target.value.trim()) { pending.current = null; setUncertain(false); }
          }} />
        {waiting
          ? <button type="button" aria-label="Остановить ответ" title="Остановить ответ" onClick={stop}>■</button>
          : <button type="submit" aria-label="Отправить сообщение" disabled={!draft.trim() || loading}>➤</button>}
      </form>
      <div className="chat-panel__footnote">История хранится в SQLite. В облачном режиме контекст передаётся Cloud.ru.</div>
    </section>
  );
}
