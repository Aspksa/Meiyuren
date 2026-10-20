import { useEffect, useState } from 'react';
import { clearHistory, loadMemory, saveMemory } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function MemoryEditor({ active }: { active: boolean }) {
  const clearChat = useAppStore((s) => s.clearChat);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setError('');
    setMessage('');
    void loadMemory(controller.signal).then((text) => {
      if (!controller.signal.aborted) setNotes(text);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Нет доступа к памяти');
    });
    return () => controller.abort();
  }, [active]);

  async function save() {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await saveMemory(notes);
      setMessage('Заметка сохранена в SQLite.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ошибка сохранения');
    } finally { setBusy(false); }
  }

  async function eraseHistory() {
    if (!window.confirm('Удалить всю историю переписки с этого компьютера?')) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await clearHistory();
      clearChat();
      setMessage('История чата удалена из SQLite.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось очистить историю');
    } finally { setBusy(false); }
  }

  return (
    <section className="memory-editor" aria-label="Память и данные">
      <h3>Память Мэйюрэн</h3>
      <p>Только заметки, которые ты сохраняешь самостоятельно. Данные остаются на компьютере.</p>
      <label htmlFor="meiyuren-memory-notes">Что Мэйюрэн должна помнить?</label>
      <textarea
        id="meiyuren-memory-notes"
        rows={3}
        maxLength={4000}
        value={notes}
        disabled={busy}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Например: мне нравятся кошки..."
      />
      <div className="memory-editor__actions">
        <button type="button" disabled={busy} onClick={() => { void save(); }}>Сохранить память</button>
        <button type="button" disabled={busy} onClick={() => { void eraseHistory(); }}>Очистить историю чата</button>
      </div>
      {error && <p className="memory-editor__error" role="alert">{error}</p>}
      {message && <p className="memory-editor__success" role="status">{message}</p>}
    </section>
  );
}
