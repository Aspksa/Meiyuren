import { useEffect, useState } from 'react';
import { getMemoryEntities, getMemoryEntity, getSemanticStatus } from '../services/chatApi';
import type { MemoryEntity, MemoryEntityDetail, SemanticStatus } from '../services/chatApi';

const KIND_LABELS: Record<MemoryEntity['kind'], string> = {
  person: 'Люди', project: 'Проекты', place: 'Места', org: 'Организации', tool: 'Инструменты',
};

const SEMANTIC_STATES: Record<string, string> = {
  ready: 'работает: поиск понимает синонимы',
  downloading: 'скачивается в режиме простоя (один раз, около 220 МБ)',
  loading: 'загружается',
  failed: 'не загрузилась, попробую снова в режиме простоя',
  'not-loaded': 'скачается, когда ты отойдёшь на 10 минут',
  'not-installed': 'не установлена: запусти setup-python.cmd',
};

/** «Люди и проекты»: что память знает о каждом названном человеке, проекте, месте. */
export function EntityPanel({ active, version }: { active: boolean; version: number }) {
  const [entities, setEntities] = useState<MemoryEntity[]>([]);
  const [open, setOpen] = useState<MemoryEntityDetail | null>(null);
  const [meaning, setMeaning] = useState<SemanticStatus | null>(null);

  useEffect(() => {
    if (!active) return;
    void getMemoryEntities().then(setEntities).catch(() => undefined);
    void getSemanticStatus().then(setMeaning).catch(() => undefined);
    // Факт добавлен, изменён или забыт: открытая карточка тоже обновляется.
    setOpen(current => {
      if (current) void getMemoryEntity(current.id).then(setOpen).catch(() => setOpen(null));
      return current;
    });
  }, [active, version]);

  const kinds = (Object.keys(KIND_LABELS) as MemoryEntity['kind'][]).filter(kind => entities.some(e => e.kind === kind));
  return <section className="entity-panel" aria-label="Люди и проекты">
    <h4>Люди и проекты</h4>
    {meaning && <p className="entity-panel__meaning">
      Модель смысла: {meaning.enabled ? (SEMANTIC_STATES[meaning.state] ?? meaning.state) : 'выключена'}
    </p>}
    {kinds.length === 0 && <p>Пока никого и ничего. Напиши, например: «Мой брат Петя учится на юриста».</p>}
    {kinds.map(kind => <div key={kind} className="entity-panel__group">
      <strong>{KIND_LABELS[kind]}</strong>
      <div className="entity-panel__chips">
        {entities.filter(e => e.kind === kind).map(entity =>
          <button type="button" key={entity.id} aria-pressed={open?.id === entity.id}
            onClick={() => void getMemoryEntity(entity.id).then(setOpen).catch(() => undefined)}>
            {entity.name}{entity.role && entity.role !== entity.name.toLowerCase() ? ' (' + entity.role + ')' : ''} · {entity.facts}
          </button>)}
      </div>
    </div>)}
    {open && <div className="entity-panel__detail">
      <div className="entity-panel__head">
        <strong>{open.name}</strong>
        <button type="button" aria-label="Закрыть" onClick={() => setOpen(null)}>×</button>
      </div>
      <ul>{open.facts.map(fact => <li key={fact.id}>{fact.content}</li>)}</ul>
      {open.related.length > 0 && <p>Связано: {open.related.map(r => r.name).join(', ')}</p>}
    </div>}
  </section>;
}
