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
const calm = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
const FRESH = 3 * 24 * 3600 * 1000;
const RECENT_RECALL = 15 * 60 * 1000;
const hash = (value: string) => [...value].reduce((h, c) => (Math.imul(31, h) + c.charCodeAt(0)) | 0, 7) >>> 0;
// Перемешивание битов: соседние строки («star1», «star2») дают далёкие числа.
const mix = (value: number) => {
  let n = Math.imul(value ^ (value >>> 16), 0x45d9f3b);
  n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
  return (n ^ (n >>> 16)) >>> 0;
};
export type SynapseFlash = { a: string; b: string; helpful: boolean; stamp: number };
// Знак созвездия каждого мозга.
export const BRAIN_SIGNS: Record<string, string> = {
  identity: '✦', episodes: '☾', goals: '⚑', habits: '∞', knowledge: '◈', relationships: '♡', projects: '⚒', decisions: '⚖',
};
const SLEEP_AFTER = 45 * 1000;
const DREAM_EVERY = 3600;
// Глубина факта: постоянная псевдо-координата z, чтобы точки не прыгали между обновлениями.
const depthOf = (id: string) => (mix(hash(id)) % 1000) / 1000;

/** Созвездие мозга: минимальное остовное дерево по положению точек на карте. */
export function constellation(points: { id: string; x: number; y: number }[]): [string, string][] {
  if (points.length < 2) return [];
  const inTree = new Set([0]);
  const best = points.map(p => Math.hypot(p.x - points[0].x, p.y - points[0].y));
  const from = points.map(() => 0);
  const lines: [string, string][] = [];
  while (inTree.size < points.length) {
    let pick = -1;
    for (let i = 0; i < points.length; i++) if (!inTree.has(i) && (pick < 0 || best[i] < best[pick])) pick = i;
    inTree.add(pick);
    lines.push([points[from[pick]].id, points[pick].id]);
    for (let i = 0; i < points.length; i++) {
      const d = Math.hypot(points[i].x - points[pick].x, points[i].y - points[pick].y);
      if (!inTree.has(i) && d < best[i]) { best[i] = d; from[i] = pick; }
    }
  }
  return lines;
}

/** Связь — плавная дуга, как нить: изгиб постоянный для пары, сторона зависит от пары. */
export function arc(a: { x: number; y: number }, b: { x: number; y: number }, bend = 0.14, side = 1) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const cx = mx - (b.y - a.y) * bend * side, cy = my + (b.x - a.x) * bend * side;
  return `M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`;
}
const sideOf = (left: string, right: string) => (hash(left < right ? left + right : right + left) & 1 ? 1 : -1);
// Толщина различает вид связи; цвет у всех один.
const FAMILY_WIDTH: Record<EdgeFamily, number> = { both: 1.25, semantic: 1, lexical: 0.85, other: 0.6 };

/** Фоновые звёзды двух слоёв: при сдвиге и масштабе они плывут медленнее карты — так видна глубина. */
const starfield = (W: number, H: number) => Array.from({ length: 140 }, (_, i) => {
  const h = mix(i + 1), v = mix(h);
  return { x: (h % 2000) / 1000 * W - W / 2, y: (v % 2000) / 1000 * H - H / 2,
    r: 0.4 + ((h >>> 5) % 10) / 10, layer: i % 2, twinkle: h % 8 === 0, delay: -(h % 5000) };
});

type Props = {
  graph: UniverseGraph | null;
  brains: readonly (readonly [string, string, string])[];
  hiddenBrains: Set<string>;
  families: Set<EdgeFamily>;
  at: number;
  selected: string;
  onSelect: (id: string) => void;
  flash?: SynapseFlash | null;
};

export function NeuralMap({ graph, brains, hiddenBrains, families, at, selected, onSelect, flash }: Props) {
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const [born, setBorn] = useState<Set<string>>(new Set());
  const known = useRef<Set<string> | null>(null);
  const [hover, setHover] = useState('');
  // Режим сна: после тишины карта темнеет, а по связям изредка пробегают «сны».
  const [asleep, setAsleep] = useState(false);
  const [dream, setDream] = useState<{ key: number; d: string } | null>(null);
  const dreamMotion = useRef<SVGAnimateMotionElement | null>(null);
  useEffect(() => {
    let timer = 0;
    const wake = () => {
      setAsleep(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setAsleep(true), SLEEP_AFTER);
    };
    const kinds = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart'] as const;
    kinds.forEach(k => window.addEventListener(k, wake, { passive: true }));
    wake();
    return () => { window.clearTimeout(timer); kinds.forEach(k => window.removeEventListener(k, wake)); };
  }, []);
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
  // Периодическое обновление приносит новый объект графа; раскладку пересчитываем, только если изменились узлы или связи.
  const layoutKey = graph ? graph.nodes.map(n => n.id).join(',') + '|' +
    graph.edges.filter(e => e.relation === 'cortex').map(e => `${e.source}-${e.target}-${e.weight}`).join(',') : '';
  const placed = useMemo(() => layoutGraph(graph?.nodes ?? [],
    (graph?.edges ?? []).filter(e => e.relation === 'cortex'), W, H), [layoutKey, W, H]);
  const placedRef = useRef(placed);
  placedRef.current = placed;
  const stars = useMemo(() => starfield(W, H), [W, H]);

  // Плавный полёт камеры к выбранному факту.
  useEffect(() => {
    const p = selected ? placedRef.current.get(selected) : undefined;
    if (!p) return;
    const from = viewRef.current;
    const k = Math.max(from.k, 1.3);
    const to = { k, x: W / 2 - p.x * k, y: H / 2 - p.y * k };
    if (calm()) { setView(to); return; }
    let frame = 0;
    const start = performance.now();
    const step = (time: number) => {
      const t = Math.min(1, (time - start) / 650), e = 1 - Math.pow(1 - t, 3);
      setView({ k: from.k + (to.k - from.k) * e, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e });
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [selected, W, H]);

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
  // Рождение факта: точки, которые только что появились (новый факт, шкала времени, фильтр), вспыхивают.
  const visibleKey = nodes.map(n => n.id).join(',');
  useEffect(() => {
    if (!graph) return;
    const ids = visibleKey ? visibleKey.split(',') : [];
    const fresh = ids.filter(id => !known.current?.has(id));
    known.current = new Set(ids);
    if (fresh.length && !calm()) setBorn(new Set(fresh));
  }, [visibleKey, graph]);
  useEffect(() => {
    if (!born.size) return;
    const timer = window.setTimeout(() => setBorn(new Set()), 1800);
    return () => window.clearTimeout(timer);
  }, [born]);

  // Импульсы бегут от выбранного факта и от фактов, которые Мэйюрэн недавно вспоминала.
  const now = Date.now();
  const firing = new Set<string>(graph?.events.filter(e => e.kind === 'recall' && now - e.timestamp < RECENT_RECALL).map(e => e.nodeId));
  if (selected) firing.add(selected);
  const pulses = edges.filter(e => e.relation === 'cortex' && (firing.has(e.source) || firing.has(e.target))).slice(0, 24)
    .flatMap(e => {
      const fromSource = firing.has(e.source);
      const a = placed.get(fromSource ? e.source : e.target), b = placed.get(fromSource ? e.target : e.source);
      const side = sideOf(e.source, e.target) * (fromSource === (e.source < e.target) ? 1 : -1);
      return a && b ? [{ key: `${e.source}:${e.target}`, d: arc(a, b, 0.14, side), delay: (hash(e.target) % 1600) / 1000 }] : [];
    });
  const isFlash = (e: GraphEdge) => !!flash && ((e.source === flash.a && e.target === flash.b) || (e.source === flash.b && e.target === flash.a));
  const counts = new Map<string, number>();
  for (const n of nodes) counts.set(n.brain, (counts.get(n.brain) ?? 0) + 1);
  const constellations = useMemo(() => brains.flatMap(([id]) => constellation(nodes
    .filter(n => n.brain === id).flatMap(n => { const p = placed.get(n.id); return p ? [{ id: n.id, ...p }] : []; }))
    .map(([a, b]) => ({ brain: id, a: placed.get(a)!, b: placed.get(b)!, key: `${a}~${b}` }))),
  [visibleKey, placed, brains]);

  // Сон: каждые несколько секунд короткая прогулка по связям, как воспоминание во сне.
  const edgesRef = useRef(edges);
  edgesRef.current = edges;
  useEffect(() => {
    if (!asleep || calm()) { setDream(null); return; }
    let seed = 1;
    const tick = () => {
      const links = edgesRef.current.filter(e => e.relation === 'cortex');
      if (!links.length) return;
      const next = new Map<string, string[]>();
      for (const e of links) {
        next.set(e.source, [...(next.get(e.source) ?? []), e.target]);
        next.set(e.target, [...(next.get(e.target) ?? []), e.source]);
      }
      const start = links[(seed * 7919) % links.length];
      const walk = [start.source, start.target];
      for (let step = 0; step < 3; step++) {
        const options = (next.get(walk[walk.length - 1]) ?? []).filter(id => !walk.includes(id));
        if (!options.length) break;
        walk.push(options[(seed + step) % options.length]);
      }
      const points = walk.flatMap(id => { const p = placedRef.current.get(id); return p ? [p] : []; });
      if (points.length >= 2) setDream({ key: seed, d: points.slice(1).map((p, i) => {
        const left = walk[i], right = walk[i + 1];
        const side = sideOf(left, right) * ((left < right) ? 1 : -1);
        return arc(points[i], p, 0.14, side).replace(i ? /^M[^Q]+/ : /$^/, '');
      }).join(' ') });
      seed++;
    };
    tick();
    const timer = window.setInterval(tick, DREAM_EVERY);
    return () => window.clearInterval(timer);
  }, [asleep]);
  useEffect(() => { dreamMotion.current?.beginElement(); }, [dream]);

  const toLocal = (event: ReactPointerEvent<SVGSVGElement> | ReactWheelEvent<SVGSVGElement>) => {
    // Через матрицу экрана: учитывает поля по краям, когда пропорции окна и карты не совпадают.
    const matrix = event.currentTarget.getScreenCTM();
    if (matrix) {
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      return { x: point.x, y: point.y };
    }
    const box = event.currentTarget.getBoundingClientRect();
    const scale = Math.max(W / box.width, H / box.height);
    return { x: (event.clientX - box.left) * scale - (box.width * scale - W) / 2, y: (event.clientY - box.top) * scale - (box.height * scale - H) / 2 };
  };
  const zoom = (factor: number, cx = W / 2, cy = H / 2) => setView(v => {
    const k = Math.max(0.6, Math.min(4, v.k * factor));
    return { k, x: cx - (cx - v.x) * k / v.k, y: cy - (cy - v.y) * k / v.k };
  });

  const parallax = (f: number) => `translate(${view.x * f} ${view.y * f}) translate(${W / 2} ${H / 2}) scale(${1 + (view.k - 1) * f}) translate(${-W / 2} ${-H / 2})`;

  return <div className={`neural-map${compact ? ' neural-map--compact' : ''}${asleep ? ' is-asleep' : ''}`}>
    {/* Небо отдельным слоем: туманности и звёзды не перерисовываются вместе с анимацией точек. */}
    <svg viewBox={`0 0 ${W} ${H}`} className="neural-map__sky" aria-hidden="true">
      <defs>
        {/* Туманность: облако с рваным краем — шум смещает и размывает градиент. */}
        <filter id="nmNebula" x="-60%" y="-60%" width="220%" height="220%">
          <feTurbulence type="fractalNoise" baseFrequency=".012" numOctaves="3" seed="7" />
          <feDisplacementMap in="SourceGraphic" scale={46 * S} />
          <feGaussianBlur stdDeviation={9 * S} />
        </filter>
        {brains.map(([id, , c]) => <radialGradient key={id} id={`nmNeb-${id}`}>
          <stop stopColor={c} stopOpacity=".11" />
          <stop offset=".5" stopColor={c} stopOpacity=".04" />
          <stop offset="1" stopColor={c} stopOpacity="0" />
        </radialGradient>)}
      </defs>
      {[0.25, 0.55].map((f, layer) => <g key={f} transform={parallax(f)} className="neural-map__stars">
        {stars.filter(st => st.layer === layer).map((st, i) => <circle key={i} cx={st.x} cy={st.y} r={st.r * S * (0.6 + f)}
          className={st.twinkle ? 'is-twinkle' : undefined} style={st.twinkle ? { animationDelay: `${st.delay}ms` } : undefined} />)}
      </g>)}
      <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        {brains.map(([id]) => {
          const a = brainAnchor(id, W, H), h = mix(hash(id));
          return <g key={id} filter="url(#nmNebula)" opacity={hiddenBrains.has(id) ? 0.25 : 1}>
            {[0, 1, 2].map(i => {
              const turn = ((h >>> (i * 4)) % 360) * Math.PI / 180, off = halo * (0.18 + i * 0.12);
              return <ellipse key={i} cx={a.x + Math.cos(turn) * off} cy={a.y + Math.sin(turn) * off}
                rx={halo * (1.35 - i * 0.2)} ry={halo * (1 - i * 0.12)} fill={`url(#nmNeb-${id})`}
                transform={`rotate(${(h >>> (i * 3)) % 180} ${a.x} ${a.y})`} />;
            })}
          </g>;
        })}
      </g>
    </svg>
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
        <radialGradient id="nmCore"><stop stopColor="#e7bf62" stopOpacity=".08" /><stop offset="1" stopColor="#e7bf62" stopOpacity="0" /></radialGradient>
        <filter id="nmGlow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="5" /></filter>
      </defs>
      <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        <circle cx={W / 2} cy={H / 2} r={250 * S} fill="url(#nmCore)" />
        <ellipse cx={W / 2} cy={H / 2} rx={W * 0.34} ry={H * 0.34} fill="none" className="neural-map__orbit" />
        {brains.map(([id, label, c]) => {
          const a = brainAnchor(id, W, H);
          const dim = hiddenBrains.has(id);
          return <g key={id} className="neural-map__brain" opacity={dim ? 0.25 : 1}>
            <text x={a.x} y={a.y + 22 * S} textAnchor="middle" fill={c} className="neural-map__sign" aria-hidden="true">{BRAIN_SIGNS[id] ?? '✦'}</text>
            <text x={a.x} y={a.y < H / 2 ? a.y - halo - 10 : a.y + halo + 12 + 15 * S} textAnchor="middle" fill={c}>
              <tspan className="neural-map__label-sign">{BRAIN_SIGNS[id] ?? '✦'}</tspan><tspan dx="5">{label}</tspan>
              <tspan dx="6" className="neural-map__count">{counts.get(id) ?? 0}</tspan></text>
          </g>;
        })}
        <g className="neural-map__constellations">
          {constellations.map(l => <line key={l.key} x1={l.a.x} y1={l.a.y} x2={l.b.x} y2={l.b.y} strokeWidth={0.7 * S}
            opacity={focus ? 0.12 : 1} />)}
        </g>
        {edges.map(e => {
          const a = placed.get(e.source), b = placed.get(e.target);
          if (!a || !b) return null;
          const family = edgeFamily(e);
          const lit = !focus || (near.has(e.source) && near.has(e.target) && (e.source === focus || e.target === focus));
          const learned = e.adjustment ?? 0;
          const flashing = isFlash(e);
          const touches = !!focus && (e.source === focus || e.target === focus);
          const side = sideOf(e.source, e.target) * (e.source < e.target ? 1 : -1);
          return <path key={`${e.relation}:${e.source}:${e.target}${flashing ? `:${flash!.stamp}` : ''}`} d={arc(a, b, 0.14, side)}
            className={`neural-map__edge neural-map__edge--${family}${touches ? ' is-lit' : ''}${learned > 0 ? ' is-learned' : learned < 0 ? ' is-weakened' : ''}${flashing ? (flash!.helpful ? ' is-flash-up' : ' is-flash-down') : ''}`}
            strokeWidth={(0.5 + Math.min(1, e.weight) * 1.3) * FAMILY_WIDTH[family] * (touches ? 1.6 : 1) * S}
            opacity={flashing || touches ? 0.95 : lit ? (family === 'other' ? 0.12 : 0.22) : 0.05} />;
        })}
        {!calm() && pulses.map(p => <circle key={p.key} r={2.6 * S} className="neural-map__pulse">
          <animateMotion dur="1.6s" begin={`-${p.delay}s`} repeatCount="indefinite" path={p.d} />
        </circle>)}
        {flash && !flash.helpful && !calm() && (() => {
          const a = placed.get(flash.a), b = placed.get(flash.b);
          if (!a || !b) return null;
          return <g key={flash.stamp} className="neural-map__sparks">
            {Array.from({ length: 8 }, (_, i) => {
              const t = (i + 0.5) / 8, x = a.x + (b.x - a.x) * t, y = a.y + (b.y - a.y) * t;
              return <circle key={i} cx={x} cy={y} r={2 * S} style={{ ['--dx' as string]: `${((i * 37) % 21) - 10}px`, ['--dy' as string]: `${12 + (i * 13) % 14}px`, animationDelay: `${i * 40}ms` }} />;
            })}
          </g>;
        })()}
        {nodes.map(n => {
          const p = placed.get(n.id);
          if (!p) return null;
          const z = depthOf(n.id);
          const r = (5 + Math.min(7, (degree.get(n.id) ?? 0) * 1.4)) * S * (0.85 + 0.3 * z);
          const c = color.get(n.brain) ?? '#e7bf62';
          const dim = focus && !near.has(n.id);
          const active = n.id === selected;
          const young = now - n.createdAt < FRESH;
          const entering = born.has(n.id);
          return <g key={n.id} className={`neural-map__node${entering ? ' is-born' : ''}`} opacity={dim ? 0.22 : 0.85 + 0.15 * z}
            style={entering ? { animationDelay: `${(hash(n.id) % 30) * 25}ms` } : undefined}
            tabIndex={0} role="button" aria-label={`Факт: ${brains.find(([id]) => id === n.brain)?.[1] ?? n.brain}, связей ${degree.get(n.id) ?? 0}`}
            onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover('')}
            onPointerUp={event => { if (!drag.current?.moved) { event.stopPropagation(); drag.current = null; onSelect(n.id); } }}
            onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(n.id); } }}>
            {(active || n.id === hover) && <circle cx={p.x} cy={p.y} r={r + 6} fill={c} opacity=".25" filter="url(#nmGlow)" />}
            {young && <circle cx={p.x} cy={p.y} r={r + 5 * S} fill="none" stroke={c} className="neural-map__fresh" />}
            {firing.has(n.id) && <circle cx={p.x} cy={p.y} r={r} fill="none" stroke={c} className="neural-map__ripple" />}
            <circle cx={p.x} cy={p.y} r={r} fill={c} stroke={active ? '#fbf3e4' : '#0d0a07'} strokeWidth={active ? 2.4 : 1.2}
              className="neural-map__dot" style={{ animationDelay: `${-(hash(n.id) % 4000)}ms` }} />
          </g>;
        })}
      </g>
      <rect x={-W} y={-H} width={W * 3} height={H * 3} className="neural-map__night" pointerEvents="none" />
      {asleep && dream && <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`} className="neural-map__dream" pointerEvents="none">
        <path key={`t${dream.key}`} d={dream.d} pathLength={1} className="neural-map__dream-trail" strokeWidth={1.6 * S} />
        <circle key={`c${dream.key}`} r={3.4 * S} className="neural-map__dream-spark">
          <animateMotion ref={dreamMotion} dur="2.6s" begin="indefinite" fill="freeze" path={dream.d} />
        </circle>
      </g>}
      {!nodes.length && <text x={W / 2} y={H / 2} textAnchor="middle" className="neural-map__empty">
        {graph ? 'Здесь появятся факты, когда Мэйюрэн что-нибудь запомнит' : 'Загружаю карту…'}
      </text>}
    </svg>
    <div className="neural-map__sleep" aria-hidden={!asleep}>☾ Мэйюрэн дремлет<span> · коснитесь карты</span></div>
    <div className="neural-map__zoom" role="group" aria-label="Масштаб карты">
      <button type="button" onClick={() => zoom(1.25)} aria-label="Приблизить">+</button>
      <button type="button" onClick={() => zoom(1 / 1.25)} aria-label="Отдалить">−</button>
      <button type="button" onClick={() => setView({ x: 0, y: 0, k: 1 })} aria-label="Показать всю карту">⤢</button>
    </div>
  </div>;
}
