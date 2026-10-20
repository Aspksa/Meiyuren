import { FormEvent, useEffect, useRef, useState } from 'react';
import { avatarUrl } from '../lib/avatars';
import { startingPosition } from '../lib/position';
import { loadHistory, sendMessage } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function ChatPanel() {
  const chatOpen = useAppStore((s) => s.chatOpen);
  const closeChat = useAppStore((s) => s.closeChat);
  const messages = useAppStore((s) => s.messages);
  const setMessages = useAppStore((s) => s.setMessages);
  const greetingEnabled = useAppStore((s) => s.greetingEnabled);
  const position = useAppStore((s) => s.position);
  const size = useAppStore((s) => s.size);
  const avatarId = useAppStore((s) => s.avatarId);
  const [draft, setDraft] = useState('');
  const [waiting, setWaiting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingRef = useRef<{ text: string; id: string } | null>(null);
  const [uncertain, setUncertain] = useState(false);

  useEffect(() => {
    if (!chatOpen) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    void loadHistory(controller.signal).then((rows) => {
      if (!controller.signal.aborted) setMessages(rows);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Ошибка истории');
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [chatOpen, setMessages]);

  useEffect(() => {
    if (chatOpen && !waiting && !loading) inputRef.current?.focus();
  }, [chatOpen, waiting, loading]);

  useEffect(() => {
    if (chatOpen) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, waiting, chatOpen]);

  if (!chatOpen) return null;

  const avatarX = (position ?? startingPosition(size, window.innerWidth, window.innerHeight)).x;
  const side = avatarX + size / 2 > window.innerWidth / 2 ? 'left' : 'right';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || waiting || loading) return;
    // Один и тот же ID на повторную попытку: backend не создаст второй платный запрос.
    if (!pendingRef.current || pendingRef.current.text !== text) {
      pendingRef.current = { text, id: crypto.randomUUID() };
    }
    setWaiting(true);
    setError('');
    try {
      const exchange = await sendMessage(text, pendingRef.current.id);
      const existing = useAppStore.getState().messages;
      const ids = new Set([exchange.user.id, exchange.assistant.id]);
      setMessages([...existing.filter((message) => !ids.has(message.id)), exchange.user, exchange.assistant]);
      pendingRef.current = null;
      setUncertain(false);
      setDraft('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось отправить сообщение');
      setUncertain(true);
      // Текст и ID сохраняются: повтор не создаст второй платный запрос.
    } finally {
      setWaiting(false);
    }
  }

  return (
    <section className={`chat-panel chat-panel--${side}`} role="dialog" aria-label="Чат с Мэйюрэн">
      <header className="panel-header">
        <span className="panel-header__mark"><img className="panel-header__portrait" src={avatarUrl(avatarId)} alt="" /></span>
        <div>
          <strong>Мэйюрэн</strong>
          <span className="panel-header__sub">Python · SQLite · Cloud.ru / демо</span>
        </div>
        <button className="icon-button panel-header__close" onClick={closeChat} aria-label="Закрыть чат" type="button">×</button>
      </header>
      <div className="chat-panel__messages" ref={listRef} aria-live="polite" aria-relevant="additions text">
        {loading && <div className="chat-panel__empty">Загружаю историю…</div>}
        {!loading && messages.length === 0 && <div className="chat-panel__empty">{greetingEnabled ? 'Привет! Я Мэйюрэн ✨ Напиши мне сообщение.' : 'Пока нет сообщений.'}</div>}
        {!loading && messages.map((item) => (
          <div className={`message message--${item.role}`} key={item.id}>
            <div className="message__text">{item.text}</div>
            <span className="message__time">{new Date(item.sentAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        ))}
        {waiting && <div className="message message--assistant"><div className="message__text">Мэйюрэн печатает…</div></div>}
      </div>
      {error && <p className="chat-panel__error" role="alert">{error}</p>}
      {uncertain && !waiting && <button type="button" className="chat-panel__new-request"
        onClick={() => {
          if (window.confirm('Создать НОВЫЙ запрос? Если Cloud.ru уже обработал предыдущий, возможна повторная оплата.')) {
            pendingRef.current = null;
            setUncertain(false);
            setError('Теперь можно отправить новый запрос. Предыдущий ответ мог быть обработан Cloud.ru.');
          }
        }}>Создать новый запрос (возможно повторное списание)</button>}
      <form className="chat-panel__composer" onSubmit={(event) => { void submit(event); }}>
        <input
          ref={inputRef}
          aria-label="Сообщение"
          placeholder="Напиши Мэйюрэн…"
          value={draft}
          maxLength={2000}
          onChange={(event) => {
            setDraft(event.target.value);
            if (pendingRef.current?.text !== event.target.value.trim()) {
              pendingRef.current = null;
              setUncertain(false);
            }
          }}
          disabled={waiting || loading}
        />
        <button type="submit" aria-label="Отправить сообщение" disabled={!draft.trim() || waiting || loading}>➤</button>
      </form>
      <div className="chat-panel__footnote">История хранится локально. Провайдер выбирается в меню Cloud.ru.</div>
    </section>
  );
}
