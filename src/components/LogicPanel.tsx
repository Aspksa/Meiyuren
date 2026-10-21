import { useEffect, useState } from 'react';
import { getInferences, rejectInference } from '../services/chatApi';
import type { Inference } from '../services/chatApi';

const KIND_LABELS: Record<Inference['kind'], string> = {
  conflict: 'Противоречия', overdue: 'Прошедшие сроки', time: 'Сроки', chain: 'Связи',
  helps: 'Что помогает целям', rule: 'Правила',
};

/** «Логика»: что мозги вывели сами, из каких фактов, и кнопка «неверно». */
export function LogicPanel({ active, version }: { active: boolean; version: number }) {
  const [items, setItems] = useState<Inference[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return;
    void getInferences().then(setItems).catch(() => undefined);
  }, [active, version]);

  async function reject(id: string) {
    try {
      await rejectInference(id);
      setItems(value => value.filter(item => item.id !== id));
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось отклонить вывод');
    }
  }

  const kinds = (Object.keys(KIND_LABELS) as Inference['kind'][]).filter(kind => items.some(i => i.kind === kind));
  return <section className="logic-panel" aria-label="Логика">
    <h4>Логика</h4>
    <p>Выводы, которые мозги сделали сами из ваших фактов. Это не ваши слова: каждый вывод
      показывает основания и исчезает вместе с ними. Неверный вывод можно отклонить.</p>
    {items.length === 0 && <p className="logic-panel__empty">Пока выводов нет. Они появятся после режима простоя.</p>}
    {error && <p role="alert">{error}</p>}
    {kinds.map(kind => <div key={kind} className="logic-panel__group">
      <strong>{KIND_LABELS[kind]}</strong>
      <ul>
        {items.filter(item => item.kind === kind).map(item => <li key={item.id}>
          <span>{item.content}</span>
          <small>потому что {item.because.map(p => '«' + p.content + '»').join(' + ')}</small>
          <button type="button" title="Неверный вывод: больше не появится" onClick={() => void reject(item.id)}>👎 неверно</button>
        </li>)}
      </ul>
    </div>)}
  </section>;
}
