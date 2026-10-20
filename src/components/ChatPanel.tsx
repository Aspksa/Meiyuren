import { FormEvent, useEffect, useRef, useState } from 'react';
import { avatarUrl } from '../lib/avatars';
import { startingPosition } from '../lib/position';
import { replyAfterDelay } from '../services/replies';
import { useAppStore } from '../store/useAppStore';

export function ChatPanel() {
  const chatOpen = useAppStore((s) => s.chatOpen);
  const closeChat = useAppStore((s) => s.closeChat);
  const messages = useAppStore((s) => s.messages);
  const addMessage = useAppStore((s) => s.addMessage);
  const position = useAppStore((s) => s.position);
  const size = useAppStore((s) => s.size);
  const avatarId = useAppStore((s) => s.avatarId);
  const [draft, setDraft] = useState('');
  const [waiting, setWaiting] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (chatOpen && !waiting) inputRef.current?.focus();
  }, [chatOpen, waiting]);

  useEffect(() => {
    if (chatOpen) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, waiting, chatOpen]);

  if (!chatOpen) return null;

  // Чат открывается с той стороны, где нет аватара, чтобы не закрывать её собой.
  const avatarX = (position ?? startingPosition(size, window.innerWidth, window.innerHeight)).x;
  const side = avatarX + size / 2 > window.innerWidth / 2 ? 'left' : 'right';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || waiting) return;
    setDraft('');
    const questionId = addMessage('user', text);
    setWaiting(true);
    try {
      const answer = await replyAfterDelay(text);
      // Если чат очистили, пока шёл ответ, вопроса уже нет и отвечать некому.
      if (useAppStore.getState().messages.some((item) => item.id === questionId)) {
        addMessage('assistant', answer);
      }
    } finally {
      // Фокус вернёт эффект выше, когда поле снова станет активным.
      setWaiting(false);
    }
  }

  return (
    <section className={`chat-panel chat-panel--${side}`} role="dialog" aria-label="Чат с Мэйюрэн">
      <header className="panel-header">
        <span className="panel-header__mark"><img className="panel-header__portrait" src={avatarUrl(avatarId)} alt="" /></span>
        <div>
          <strong>Мэйюрэн</strong>
          <span className="panel-header__sub">Демо-чат · локальные ответы</span>
        </div>
        <button className="icon-button panel-header__close" onClick={closeChat} aria-label="Закрыть чат" type="button">×</button>
      </header>
      <div className="chat-panel__messages" ref={listRef} aria-live="polite" aria-relevant="additions text">
        {messages.length === 0 && (
          <div className="chat-panel__empty">Напиши мне что-нибудь. Например: «Привет!» 🌸</div>
        )}
        {messages.map((item) => (
          <div className={`message message--${item.role}`} key={item.id}>
            <div className="message__text">{item.text}</div>
            <span className="message__time">{new Date(item.sentAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        ))}
        {waiting && <div className="message message--assistant"><div className="message__text">Печатает<span className="dots">…</span></div></div>}
      </div>
      <form className="chat-panel__composer" onSubmit={submit}>
        <input
          ref={inputRef}
          aria-label="Сообщение"
          placeholder="Напиши Мэйюрэн..."
          value={draft}
          maxLength={2000}
          onChange={(event) => setDraft(event.target.value)}
          disabled={waiting}
        />
        <button type="submit" aria-label="Отправить сообщение" disabled={!draft.trim() || waiting}>➤</button>
      </form>
      <div className="chat-panel__footnote">Ответы пока демонстрационные. AI API не подключён.</div>
    </section>
  );
}
