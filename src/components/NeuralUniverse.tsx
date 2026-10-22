import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './NeuralUniverse.css';
import { NeuralMap, edgeFamily } from './NeuralMap';
import { plural } from '../lib/plural';
import type { EdgeFamily, SynapseFlash } from './NeuralMap';
import {
  getEvolutionLab, getNodeCard, getQualityGate, getSnapshots, getUniverseGraph, getUniverseStatus, sendSynapseFeedback,
} from '../services/neuralApi';
import type { EvolutionLab, Health, NodeCard, QualityGate, Snapshot, UniverseGraph, UniverseStatus } from '../services/neuralApi';

/** Восемь мозгов: ключ, подпись и цвет на карте (тёплая палитра темы). */
export const BRAINS = [
  ['identity', 'Личность', '#f3d891'], ['episodes', 'События', '#f29e6b'],
  ['goals', 'Цели', '#ef7b7b'], ['habits', 'Привычки', '#a6d48c'],
  ['knowledge', 'Знания', '#74c7d6'], ['relationships', 'Люди', '#ea98c6'],
  ['projects', 'Проекты', '#b9a0f2'], ['decisions', 'Решения', '#f5efe0'],
] as const;
const brainName = (id: string) => BRAINS.find(([key]) => key === id)?.[1] ?? id;
const brainColor = (id: string) => BRAINS.find(([key]) => key === id)?.[2] ?? '#e7bf62';

const FAMILIES: { id: EdgeFamily; label: string; hint: string }[] = [
  { id: 'both', label: 'Слова и смысл', hint: 'Есть общие слова, и модель смысла считает факты близкими' },
  { id: 'semantic', label: 'По смыслу', hint: 'Общих слов нет, но смысл близок: «кофе» и «эспрессо»' },
  { id: 'lexical', label: 'Общие слова', hint: 'Минимум два общих значимых слова' },
  { id: 'other', label: 'Темы и Cloud.ru', hint: 'Старые связи памяти: общая тема или платные векторы Cloud.ru' },
];
type Tab = 'map' | 'brains' | 'learning' | 'journal';
const TABS: [Tab, string][] = [['map', 'Карта'], ['brains', 'Мозги'], ['learning', 'Обучение'], ['journal', 'Журнал']];
const STRATEGIES: Record<string, string> = { balanced: 'сбалансированная', focused: 'точная', context: 'контекстная' };
const strategyName = (id?: string) => (id && STRATEGIES[id]) || id || '—';
const when = (value: number) => new Date(value).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export function NeuralUniverse({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<UniverseStatus | null>(null);
  const [graph, setGraph] = useState<UniverseGraph | null>(null);
  const [quality, setQuality] = useState<QualityGate | null>(null);
  const [lab, setLab] = useState<EvolutionLab | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<Tab>('map');
  const [hiddenBrains, setHiddenBrains] = useState<Set<string>>(new Set());
  const [families, setFamilies] = useState<Set<EdgeFamily>>(new Set(['both', 'semantic', 'lexical', 'other']));
  const [timePercent, setTimePercent] = useState(100);
  const [selected, setSelected] = useState('');
  const [card, setCard] = useState<NodeCard | null>(null);
  const [cardError, setCardError] = useState('');
  const [voting, setVoting] = useState('');
  const cardRef = useRef<HTMLElement>(null);
  const [flash, setFlash] = useState<SynapseFlash | null>(null);
  const [playing, setPlaying] = useState(false);

  // ▶ проигрывает рост памяти: шкала времени идёт от первого факта до сегодня.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const start = performance.now();
    const step = (time: number) => {
      const t = Math.min(1, (time - start) / 9000);
      setTimePercent(Math.round(t * 100));
      if (t < 1) frame = requestAnimationFrame(step); else setPlaying(false);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextStatus, nextGraph] = await Promise.all([getUniverseStatus(signal), getUniverseGraph(signal)]);
      if (signal?.aborted) return;
      setStatus(nextStatus); setGraph(nextGraph); setError('');
    } catch (cause) {
      if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'Нет связи с Python-сервером');
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const { signal } = controller;
    void refresh(signal);
    void getQualityGate(signal).then(setQuality).catch(() => undefined);
    void getEvolutionLab(signal).then(setLab).catch(() => undefined);
    void getSnapshots(false, signal).then(setSnapshots).catch(() => undefined);
    const stream = new EventSource('/api/memory/universe/events');
    // Сервер шлёт событие только при изменении связности; граф перечитываем лишь тогда, когда оно не первое.
    let seen = false;
    stream.addEventListener('health', message => {
      try {
        setHealth(JSON.parse((message as MessageEvent).data) as Health);
        if (seen) void refresh(signal);
        seen = true;
      } catch { /* повреждённое событие пропускаем */ }
    });
    const interval = window.setInterval(() => void refresh(signal), 15000);
    return () => { controller.abort(); stream.close(); window.clearInterval(interval); };
  }, [open, refresh]);

  useEffect(() => {
    if (!selected) { setCard(null); setCardError(''); return; }
    const controller = new AbortController();
    setCardError('');
    // Карточка прежнего факта не остаётся рядом с новым, пока грузится новая.
    setCard(previous => previous?.item.id === selected ? previous : null);
    void getNodeCard(selected, controller.signal).then(setCard).catch(cause => {
      if (!controller.signal.aborted) { setCard(null); setCardError(cause instanceof Error ? cause.message : 'Факт недоступен'); }
    });
    return () => controller.abort();
  }, [selected]);

  // Факт изменили (например, пока панель была закрыта): перечитываем карточку.
  const selectedUpdatedAt = graph?.nodes.find(n => n.id === selected)?.updatedAt;
  const cardUpdatedAt = card?.item.id === selected ? card.item.updatedAt : undefined;
  useEffect(() => {
    if (!selected || selectedUpdatedAt === undefined || cardUpdatedAt === undefined || selectedUpdatedAt === cardUpdatedAt) return;
    const controller = new AbortController();
    void getNodeCard(selected, controller.signal).then(setCard).catch(() => undefined);
    return () => controller.abort();
  }, [selected, selectedUpdatedAt, cardUpdatedAt]);

  // Факт пропал с карты: проверяем, жив ли он (он может быть просто вне 300 показанных), и закрываем карточку, если забыт.
  useEffect(() => {
    if (!selected || !graph || graph.nodes.some(n => n.id === selected)) return;
    const controller = new AbortController();
    void getNodeCard(selected, controller.signal).then(setCard).catch(() => {
      if (!controller.signal.aborted) setSelected('');
    });
    return () => controller.abort();
  }, [graph, selected]);

  // На узком экране карточка под картой: после выбора факта прокручиваем к ней.
  const cardId = card?.item.id;
  useEffect(() => {
    if (cardId && window.matchMedia?.('(max-width: 1100px)').matches) cardRef.current?.scrollIntoView({ block: 'start' });
  }, [cardId]);

  const earliest = useMemo(() => graph?.nodes.reduce((v, n) => Math.min(v, n.createdAt), Date.now()) ?? Date.now(), [graph]);
  const at = timePercent === 100 ? Number.MAX_SAFE_INTEGER : earliest + (Date.now() - earliest) * timePercent / 100;
  const brainStats = useMemo(() => {
    const links = new Map<string, number>();
    const pairs = new Map<string, number>();
    const brainOf = new Map(graph?.nodes.map(n => [n.id, n.brain]) ?? []);
    for (const edge of graph?.edges ?? []) {
      const a = brainOf.get(edge.source), b = brainOf.get(edge.target);
      if (!a || !b) continue;
      links.set(a, (links.get(a) ?? 0) + 1); links.set(b, (links.get(b) ?? 0) + 1);
      if (a !== b) { const key = [a, b].sort().join('|'); pairs.set(key, (pairs.get(key) ?? 0) + 1); }
    }
    return { links, pairs };
  }, [graph]);

  if (!open) return null;
  const counts = status?.network.brains ?? {};
  const cortex = status?.neuralCortex;
  const total = BRAINS.reduce((sum, [id]) => sum + (counts[id] ?? 0), 0);
  const maxCount = Math.max(1, ...BRAINS.map(([id]) => counts[id] ?? 0));
  const meaningLinks = (cortex?.semanticEdges ?? 0) + (cortex?.bothEdges ?? 0);
  const familyCount = (family: EdgeFamily) => graph?.edges.filter(e => edgeFamily(e) === family).length ?? 0;

  const toggle = <T,>(set: Set<T>, value: T) => { const next = new Set(set); if (next.has(value)) next.delete(value); else next.add(value); return next; };
  const openOnMap = (id: string) => { setTab('map'); setSelected(id); };
  const vote = async (other: string, helpful: boolean) => {
    if (!card || card.item.id !== selected) return;
    setVoting(other + helpful);
    try {
      await sendSynapseFeedback(card.item.id, other, helpful);
      setFlash({ a: card.item.id, b: other, helpful, stamp: Date.now() });
      setCard(await getNodeCard(card.item.id));
      void refresh();
    } catch (cause) {
      setCardError(cause instanceof Error ? cause.message : 'Оценка не сохранилась');
    } finally { setVoting(''); }
  };

  const metrics: [string, number | string, string][] = [
    ['Фактов', status ? total : '—', 'Подтверждённые воспоминания во всех мозгах'],
    ['Связей нейросети', cortex?.edges ?? '—', 'Связи Cortex между фактами разных мозгов'],
    ['По смыслу', cortex ? meaningLinks : '—', 'Связи, найденные локальной моделью смысла'],
    ['Выучено синапсов', cortex?.learnedSynapses ?? '—', 'Связи, вес которых изменили ваши 👍 и 👎'],
    ['Векторов смысла', status?.network.semanticVectors ?? '—', 'Факты, которые модель смысла уже прочитала'],
  ];

  return <section className="neural-universe" role="dialog" aria-modal="false" aria-labelledby="neural-universe-title">
    <header className="neural-universe__head">
      <div className="neural-universe__mark" aria-hidden="true">✦</div>
      <div className="neural-universe__title">
        <small>Память Мэйюрэн</small>
        <h2 id="neural-universe-title">Нейросеть</h2>
      </div>
      <span className={`neural-universe__pill${health && !health.healthy ? ' is-warning' : ''}`} role="status">
        <i />{health ? (health.healthy ? 'Связи целы' : `Найдено повреждений: ${health.orphanLinks + health.orphanVectors}`) : 'Проверяю связи…'}
      </span>
      <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть нейросеть">×</button>
    </header>

    <div className="neural-universe__metrics">
      {metrics.map(([label, value, hint]) => <div key={label} className="neural-universe__metric" title={hint}>
        <strong>{value}</strong><span>{label}</span>
      </div>)}
    </div>
    {error && <p className="neural-universe__error" role="alert">{error}. Показаны последние полученные данные.</p>}

    <nav className="neural-universe__tabs" role="tablist" aria-label="Разделы нейросети">
      {TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={tab === id}
        className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>{label}</button>)}
    </nav>

    {tab === 'map' && <div className="neural-universe__map-layout">
      <div className="neural-universe__canvas">
        <div className="neural-universe__filters">
          <div className="neural-universe__chips" role="group" aria-label="Мозги на карте">
            {BRAINS.map(([id, label, color]) => <button key={id} type="button" aria-pressed={!hiddenBrains.has(id)}
              onClick={() => setHiddenBrains(set => toggle(set, id))} style={{ ['--chip' as string]: color }}>
              <i />{label}
            </button>)}
          </div>
          <div className="neural-universe__chips neural-universe__chips--edges" role="group" aria-label="Виды связей">
            {FAMILIES.map(f => <button key={f.id} type="button" aria-pressed={families.has(f.id)} title={f.hint}
              onClick={() => setFamilies(set => toggle(set, f.id))}>
              <b className={`neural-universe__swatch neural-universe__swatch--${f.id}`} />{f.label}<span>{familyCount(f.id)}</span>
            </button>)}
          </div>
        </div>
        <NeuralMap graph={graph} brains={BRAINS} hiddenBrains={hiddenBrains} families={families}
          at={at} selected={selected} onSelect={setSelected} flash={flash} />
        <div className="neural-universe__timeline">
          <button type="button" className="neural-universe__play" onClick={() => setPlaying(p => !p)}
            aria-label={playing ? 'Остановить показ роста памяти' : 'Показать, как росла память'}>{playing ? '❚❚' : '▶'}</button>
          <label>
            <span>Как росла память: <strong>{timePercent === 100 ? 'сейчас' : when(at)}</strong></span>
            <input type="range" min="0" max="100" value={timePercent} onChange={e => { setPlaying(false); setTimePercent(Number(e.target.value)); }} />
          </label>
        </div>
        {graph?.truncated && <p className="neural-universe__hint">Показаны 300 самых свежих фактов.</p>}
      </div>

      <aside ref={cardRef} className="neural-universe__card" aria-live="polite">
        {!selected && <div className="neural-universe__card-empty">
          <h3>Как читать карту</h3>
          <p>Каждая точка — факт, который запомнила Мэйюрэн. Цвет показывает мозг, размер — число связей.</p>
          <p>Нажмите на точку, чтобы прочитать факт и увидеть, почему он связан с другими. Оценки 👍 и 👎 учат нейросеть, какие связи полезны.</p>
          <p className="neural-universe__muted">Колёсико мыши меняет масштаб, перетаскивание сдвигает карту.</p>
        </div>}
        {selected && cardError && <p className="neural-universe__error">{cardError}</p>}
        {selected && card?.item.id === selected && <>
          <div className="neural-universe__card-head">
            <span className="neural-universe__brain-tag" style={{ ['--chip' as string]: brainColor(card.item.brain) }}><i />{brainName(card.item.brain)}</span>
            <button type="button" className="icon-button" onClick={() => setSelected('')} aria-label="Закрыть карточку факта">×</button>
          </div>
          <blockquote>{card.item.content}</blockquote>
          <small className="neural-universe__muted">Запомнено {when(card.item.createdAt)}</small>
          <h4>Связи <span>{card.links.length}</span></h4>
          {!card.links.length && <p className="neural-universe__muted">Связей пока нет. Они появятся, когда в других мозгах найдётся факт с общими словами или близким смыслом.</p>}
          <ul className="neural-universe__links">
            {card.links.map(link => <li key={link.id}>
              <button type="button" className="neural-universe__link-text" onClick={() => setSelected(link.id)}>
                <span className="neural-universe__brain-tag" style={{ ['--chip' as string]: brainColor(link.brain) }}><i />{brainName(link.brain)}</span>
                {link.content}
              </button>
              <div className="neural-universe__why">
                <b className={`neural-universe__swatch neural-universe__swatch--${link.kind}`} />
                {link.kind === 'lexical' && <>Общие слова: {link.terms.join(', ')}</>}
                {link.kind === 'semantic' && <>Близко по смыслу: {Math.round((link.meaning ?? 0) * 100)}%</>}
                {link.kind === 'both' && <>Слова ({link.terms.join(', ')}) и смысл {Math.round((link.meaning ?? 0) * 100)}%</>}
              </div>
              <div className="neural-universe__strength">
                <meter min={0} max={1} value={link.weight} aria-label={`Сила связи ${Math.round(link.weight * 100)}%`} />
                {link.adjustment ? <span>{link.adjustment > 0 ? 'усилена' : 'ослаблена'} оценками</span> : null}
                <button type="button" disabled={!!voting} onClick={() => void vote(link.id, true)} aria-label="Полезная связь" title="Полезная связь">👍</button>
                <button type="button" disabled={!!voting} onClick={() => void vote(link.id, false)} aria-label="Лишняя связь" title="Лишняя связь">👎</button>
              </div>
            </li>)}
          </ul>
        </>}
      </aside>
    </div>}

    {tab === 'brains' && <div className="neural-universe__brains">
      {BRAINS.map(([id, label, color]) => <button key={id} type="button" className="neural-universe__brain"
        style={{ ['--chip' as string]: color }} onClick={() => { setHiddenBrains(new Set(BRAINS.map(([key]) => key).filter(key => key !== id))); setTab('map'); }}>
        <span className="neural-universe__brain-tag"><i />{label}</span>
        <strong>{counts[id] ?? 0}</strong>
        <span className="neural-universe__bar"><i style={{ width: `${((counts[id] ?? 0) / maxCount) * 100}%` }} /></span>
        <small>{plural(brainStats.links.get(id) ?? 0, 'связь', 'связи', 'связей')} · {plural(lab?.branchesByBrain[id] ?? 0, 'ветвь', 'ветви', 'ветвей')}</small>
      </button>)}
      <div className="neural-universe__pairs">
        <h3>Какие мозги связаны сильнее всего</h3>
        {[...brainStats.pairs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([key, value]) => {
          const [a, b] = key.split('|');
          return <p key={key}><span style={{ color: brainColor(a) }}>{brainName(a)}</span> ↔ <span style={{ color: brainColor(b) }}>{brainName(b)}</span><strong>{value}</strong></p>;
        })}
        {!brainStats.pairs.size && <p className="neural-universe__muted">Связей между мозгами пока нет.</p>}
        <p className="neural-universe__muted">Нажмите на мозг, чтобы увидеть на карте только его факты.</p>
      </div>
    </div>}

    {tab === 'learning' && <div className="neural-universe__panels">
      <article>
        <h3>Как нейросеть учится</h3>
        <p>Связь появляется, когда у фактов из разных мозгов есть общие слова или близкий смысл. Модель смысла работает прямо в приложении, без интернета.</p>
        <dl>
          <div><dt>Общие слова</dt><dd>{cortex?.lexicalEdges ?? 0}</dd></div>
          <div><dt>Только смысл</dt><dd>{cortex?.semanticEdges ?? 0}</dd></div>
          <div><dt>Слова и смысл</dt><dd>{cortex?.bothEdges ?? 0}</dd></div>
          <div><dt>Выучено от 👍/👎</dt><dd>{cortex?.learnedSynapses ?? 0}</dd></div>
        </dl>
        {!status?.network.semanticVectors && <p className="neural-universe__muted">Модель смысла ещё не прочитала факты. Включите её в настройках памяти: она скачается один раз в режиме простоя.</p>}
      </article>
      <article>
        <h3>Качество памяти</h3>
        {quality?.sufficientEvidence
          ? <p className="neural-universe__big">{Math.round((quality.activeScore ?? 0) * 100)}%<span>полезных воспоминаний в топ-3 · {(quality.deltaVsBaseline ?? 0) >= 0 ? '+' : ''}{((quality.deltaVsBaseline ?? 0) * 100).toFixed(1)} п.п. к базовой стратегии</span></p>
          : <><p>Пока мало оценок: {quality?.cases ?? 0} из {quality?.minimumCases ?? 6}.</p>
            <span className="neural-universe__bar"><i style={{ width: `${Math.min(100, ((quality?.cases ?? 0) / (quality?.minimumCases ?? 6)) * 100)}%` }} /></span>
            <p className="neural-universe__muted">Ставьте 👍 и 👎 воспоминаниям в чате, и здесь появится честная оценка.</p></>}
      </article>
      <article>
        <h3>Эволюция стратегии</h3>
        <p>Поколение <strong>{lab?.evolution.generation ?? '—'}</strong> · стратегия <strong>{strategyName(lab?.evolution.strategy)}</strong></p>
        <p className="neural-universe__muted">Оценок: {lab?.evolution.feedbackCases ?? 0} · подмозгов: {lab?.evolution.microbrains ?? 0}</p>
        <ol className="neural-universe__trials">
          {lab?.trials.slice(0, 8).map((trial, i) => <li key={i} className={trial.selected ? 'is-selected' : ''}>
            <span>#{trial.generation} {strategyName(trial.strategy)}</span><meter min={0} max={1} value={trial.score} /><b>{trial.score.toFixed(2)}</b>
          </li>)}
        </ol>
        {!lab?.trials.length && <p className="neural-universe__muted">Испытаний пока не было.</p>}
      </article>
    </div>}

    {tab === 'journal' && <div className="neural-universe__journal">
      <div className="neural-universe__journal-head">
        <h3>Что происходило с памятью</h3>
        <button type="button" onClick={() => void getSnapshots(true).then(setSnapshots)}>Сохранить снимок</button>
        <span className="neural-universe__muted">Снимков: {snapshots.length}</span>
      </div>
      <ol>
        {graph?.events.map((event, i) => {
          const node = graph.nodes.find(n => n.id === event.nodeId);
          const verb = event.kind === 'recall' ? 'вспомнила факт' : event.action === 'created' || event.action === 'approved' ? 'запомнила факт' : 'изменила факт';
          return <li key={i}>
            <time>{when(event.timestamp)}</time>
            <span className="neural-universe__brain-tag" style={{ ['--chip' as string]: brainColor(node?.brain ?? '') }}><i />{brainName(node?.brain ?? '')}</span>
            <span>Мэйюрэн {verb}</span>
            {node && <button type="button" onClick={() => openOnMap(event.nodeId)}>Показать на карте</button>}
          </li>;
        })}
      </ol>
      {!graph?.events.length && <p className="neural-universe__muted">Журнал пока пуст.</p>}
    </div>}
  </section>;
}
