import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from 'react';
import { brainAnchor, layoutGraph } from '../lib/neuralLayout';
import type { GraphEdge, UniverseGraph } from '../services/neuralApi';

export type EdgeFamily = 'lexical' | 'semantic' | 'both' | 'other';
export const edgeFamily = (edge: GraphEdge): EdgeFamily =>
  edge.relation === 'cortex' ? (edge.kind ?? 'lexical') : 'other';

// Широкий экран — горизонтальная карта, телефон — вертикальная, чтобы точки не мельчали.
const WIDE = { W: 1000, H: 640, scale: 1 }, TALL = { W: 600, H: 860, scale: 1.7 };
const compactQuery = '(max-width: 600px)';

type Props = {
  graph: UniverseGraph | null;
  brains: readonly (readonly [string, string, string])[];
  hiddenBrains: Set<string>;
  families: Set<EdgeFamily>;
  at: number;
  selected: string;
  onSelect: (id: string) => void;
};

export function NeuralMap({ graph, brains, hiddenBrains, families, at, selected, onSelect }: Props) {
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [hover, setHover] = useState('');
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const color = useMemo(() => new Map(brains.map(([id, , c]) => [id, c])), [brains]);
  const [compact, setCompact] = useState(() => typeof window !== 'undefined' && window.matchMedia?.(compactQuery).matches);
  useEffect(() => {
    const media = window.matchMedia?.(compactQuery);
    if (!media) return;
    const update = () => { setCompact(media.matches); setView({ x: 0, y: 0, k: 1 }); };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const { W, H, scale: S } = compact ? TALL : WIDE;
  const halo = compact ? 78 : 72;

  // Раскладка считается по всему графу, чтобы фильтры и время не перетасовывали узлы.
  const placed = useMemo(() => layoutGraph(graph?.nodes ?? [],
    (graph?.edges ?? []).filter(e => e.relation === 'cortex'), W, H), [graph, W, H]);

  const nodes = (graph?.nodes ?? []).filter(n => n.createdAt <= at && !hiddenBrains.has(n.brain));
  const visible = new Set(nodes.map(n => n.id));
  const edges = (graph?.edges ?? []).filter(e => visible.has(e.source) && visible.has(e.target)
    && families.has(edgeFamily(e)) && (e.updatedAt ?? 0) <= at);
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const focus = hover || selected;
  const near = new Set<string>(focus ? [focus] : []);
  if (focus) for (const e of edges) {
    if (e.source === focus) near.add(e.target);
    if (e.target === focus) near.add(e.source);
  }
  const counts = new Map<string, number>();
  for (const n of nodes) counts.set(n.brain, (counts.get(n.brain) ?? 0) + 1);

  const toLocal = (event: ReactPointerEvent<SVGSVGElement> | ReactWheelEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const scale = Math.max(W / box.width, H / box.height);
    return { x: (event.clientX - box.left) * scale, y: (event.clientY - box.top) * scale };
  };
  const zoom = (factor: number, cx = W / 2, cy = H / 2) => setView(v => {
    const k = Math.max(0.6, Math.min(4, v.k * factor));
    return { k, x: cx - (cx - v.x) * k / v.k, y: cy - (cy - v.y) * k / v.k };
  });

  return <div className={`neural-map${compact ? ' neural-map--compact' : ''}`}>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Карта нейросети: факты восьми мозгов и связи между ними"
      onWheel={event => { const p = toLocal(event); zoom(event.deltaY < 0 ? 1.15 : 1 / 1.15, p.x, p.y); }}
      onPointerDown={event => { drag.current = { x: event.clientX, y: event.clientY, moved: false }; }}
      onPointerMove={event => {
        const d = drag.current;
        if (!d || !(event.buttons & 1)) return;
        const dx = event.clientX - d.x, dy = event.clientY - d.y;
        if (!d.moved && Math.hypot(dx, dy) < 4) return;
        if (!d.moved) event.currentTarget.setPointerCapture(event.pointerId);
        const box = event.currentTarget.getBoundingClientRect();
        const scale = Math.max(W / box.width, H / box.height);
        d.moved = true; d.x = event.clientX; d.y = event.clientY;
        setView(v => ({ ...v, x: v.x + dx * scale, y: v.y + dy * scale }));
      }}
      onPointerUp={() => { if (drag.current && !drag.current.moved) onSelect(''); drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      style={{ cursor: drag.current?.moved ? 'grabbing' : 'grab' }}>
      <defs>
        <radialGradient id="nmCore"><stop stopColor="#e7bf62" stopOpacity=".2" /><stop offset="1" stopColor="#e7bf62" stopOpacity="0" /></radialGradient>
        <filter id="nmGlow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="5" /></filter>
      </defs>
      <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        <circle cx={W / 2} cy={H / 2} r={250 * S} fill="url(#nmCore)" />
        <ellipse cx={W / 2} cy={H / 2} rx={W * 0.34} ry={H * 0.34} fill="none" className="neural-map__orbit" />
        {brains.map(([id, label, c]) => {
          const a = brainAnchor(id, W, H);
          const dim = hiddenBrains.has(id);
          return <g key={id} className="neural-map__brain" opacity={dim ? 0.25 : 1}>
            <circle cx={a.x} cy={a.y} r={halo} fill={c} opacity=".06" />
            <circle cx={a.x} cy={a.y} r={halo} fill="none" stroke={c} strokeOpacity=".22" strokeDasharray="2 6" />
            <text x={a.x} y={a.y < H / 2 ? a.y - halo - 10 : a.y + halo + 12 + 15 * S} textAnchor="middle" fill={c}>{label}<tspan dx="6" className="neural-map__count">{counts.get(id) ?? 0}</tspan></text>
          </g>;
        })}
        {edges.map(e => {
          const a = placed.get(e.source), b = placed.get(e.target);
          if (!a || !b) return null;
          const family = edgeFamily(e);
          const lit = !focus || (near.has(e.source) && near.has(e.target) && (e.source === focus || e.target === focus));
          const learned = e.adjustment ?? 0;
          return <line key={`${e.relation}:${e.source}:${e.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            className={`neural-map__edge neural-map__edge--${family}${learned > 0 ? ' is-learned' : learned < 0 ? ' is-weakened' : ''}`}
            strokeWidth={(0.8 + Math.min(1, e.weight) * 2.6) * S} opacity={lit ? 0.9 : 0.08} />;
        })}
        {nodes.map(n => {
          const p = placed.get(n.id);
          if (!p) return null;
          const r = (5 + Math.min(7, (degree.get(n.id) ?? 0) * 1.4)) * S;
          const c = color.get(n.brain) ?? '#e7bf62';
          const dim = focus && !near.has(n.id);
          const active = n.id === selected;
          return <g key={n.id} className="neural-map__node" opacity={dim ? 0.22 : 1}
            tabIndex={0} role="button" aria-label={`Факт: ${brains.find(([id]) => id === n.brain)?.[1] ?? n.brain}, связей ${degree.get(n.id) ?? 0}`}
            onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover('')}
            onPointerUp={event => { if (!drag.current?.moved) { event.stopPropagation(); drag.current = null; onSelect(n.id); } }}
            onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(n.id); } }}>
            {(active || n.id === hover) && <circle cx={p.x} cy={p.y} r={r + 9} fill={c} opacity=".45" filter="url(#nmGlow)" />}
            <circle cx={p.x} cy={p.y} r={r} fill={c} stroke={active ? '#fbf3e4' : '#0d0a07'} strokeWidth={active ? 2.4 : 1.2} />
          </g>;
        })}
      </g>
      {!nodes.length && <text x={W / 2} y={H / 2} textAnchor="middle" className="neural-map__empty">
        {graph ? 'Здесь появятся факты, когда Мэйюрэн что-нибудь запомнит' : 'Загружаю карту…'}
      </text>}
    </svg>
    <div className="neural-map__zoom" role="group" aria-label="Масштаб карты">
      <button type="button" onClick={() => zoom(1.25)} aria-label="Приблизить">+</button>
      <button type="button" onClick={() => zoom(1 / 1.25)} aria-label="Отдалить">−</button>
      <button type="button" onClick={() => setView({ x: 0, y: 0, k: 1 })} aria-label="Показать всю карту">⤢</button>
    </div>
  </div>;
}
