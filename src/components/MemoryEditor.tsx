import { useEffect, useState } from 'react';
import { addMemoryFact, clearHistory, getMemoryFacts, loadMemory, removeMemoryFact, saveMemory } from '../services/chatApi';
import type { MemoryFact } from '../services/chatApi';
import { useAppStore } from '../store/useAppStore';

export function MemoryEditor({ active }: { active: boolean }) {
  const clearChat = useAppStore((s) => s.clearChat);
  const [notes, setNotes] = useState('');
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [factDraft, setFactDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setError('');
    setMessage('');
    void getMemoryFacts().then((items) => { if (!controller.signal.aborted) setFacts(items); }).catch(() => undefined);
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
    if (!window.confirm('Очистить историю ОСНОВНОГО диалога? Другие диалоги сохранятся.')) return;
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

  async function addFact() {
    if (!factDraft.trim()) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const fact = await addMemoryFact(factDraft.trim());
      setFacts(items => [fact, ...items]);
      setFactDraft('');
      setMessage('Факт добавлен в память.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка'); }
    finally { setBusy(false); }
  }

  async function deleteFact(id: string) {
    if (!window.confirm('Удалить выбранный факт памяти?')) return;
    setBusy(true); setError('');
    try { await removeMemoryFact(id); setFacts(items => items.filter(item => item.id !== id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка удаления'); }
    finally { setBusy(false); }
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
      <h3>Сохранённые факты</h3>
      <p>Факты добавляются только вручную. В облачном режиме они могут передаваться Cloud.ru.</p>
      <label htmlFor="memory-fact">Новый факт</label>
      <input id="memory-fact" maxLength={500} value={factDraft} disabled={busy}
        placeholder="Например: мою кошку зовут Мия"
        onChange={event => setFactDraft(event.target.value)} />
      <button type="button" disabled={busy || !factDraft.trim()} onClick={() => void addFact()}>＋ Сохранить факт</button>
      {facts.length === 0 && <p>Сохранённых фактов пока нет.</p>}
      <ul className="memory-facts">
        {facts.map(fact => <li key={fact.id}><span>{fact.content}</span>
          <button type="button" aria-label="Удалить факт" disabled={busy}
            onClick={() => void deleteFact(fact.id)}>×</button></li>)}
      </ul>
      <div className="memory-editor__actions">
        <button type="button" disabled={busy} onClick={() => { void save(); }}>Сохранить память</button>
        <button type="button" disabled={busy} onClick={() => { void eraseHistory(); }}>Очистить историю чата</button>
      </div>
      {error && <p className="memory-editor__error" role="alert">{error}</p>}
      {message && <p className="memory-editor__success" role="status">{message}</p>}
    </section>
  );
}
