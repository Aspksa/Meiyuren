/** Детерминированная раскладка карты нейросети: мозги по кругу, факты тянутся к своему мозгу и к соседям. */
export type LayoutNode = { id: string; brain: string };
export type LayoutEdge = { source: string; target: string; weight: number };
export type Placed = { x: number; y: number };

export const BRAIN_ORDER = ['identity', 'episodes', 'goals', 'habits', 'knowledge', 'relationships', 'projects', 'decisions'] as const;

const hash = (value: string) => [...value].reduce((h, c) => (Math.imul(31, h) + c.charCodeAt(0)) | 0, 7) >>> 0;

export function brainAnchor(brain: string, width: number, height: number): Placed {
  const index = Math.max(0, BRAIN_ORDER.indexOf(brain as typeof BRAIN_ORDER[number]));
  const angle = index * Math.PI / 4 - Math.PI / 2;
  return { x: width / 2 + Math.cos(angle) * width * 0.34, y: height / 2 + Math.sin(angle) * height * 0.34 };
}

export function layoutGraph(nodes: LayoutNode[], edges: LayoutEdge[], width: number, height: number, steps = 240): Map<string, Placed> {
  const pos = nodes.map(node => {
    const anchor = brainAnchor(node.brain, width, height);
    const h = hash(node.id);
    const angle = (h % 628) / 100, spread = (18 + (h >>> 10) % 40) * Math.min(width, height) / 640;
    return { x: anchor.x + Math.cos(angle) * spread, y: anchor.y + Math.sin(angle) * spread, vx: 0, vy: 0, anchor };
  });
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const links = edges.flatMap(edge => {
    const a = index.get(edge.source), b = index.get(edge.target);
    return a === undefined || b === undefined || a === b ? [] : [{ a, b, w: Math.max(0.05, Math.min(1, edge.weight)) }];
  });
  const repel = 900 * Math.max(0.35, Math.min(1, 60 / Math.max(1, nodes.length)));
  // Факт всегда остаётся внутри облака своего мозга; связи лишь смещают его к соседям.
  const reach = Math.min(width, height) * 0.1;
  for (let step = 0; step < steps; step += 1) {
    const heat = 1 - step / steps;
    for (let i = 0; i < pos.length; i += 1) {
      const p = pos[i];
      for (let j = i + 1; j < pos.length; j += 1) {
        const q = pos[j];
        let dx = p.x - q.x, dy = p.y - q.y;
        let d2 = dx * dx + dy * dy;
        if (d2 > 22000) continue;
        if (d2 < 0.01) { dx = 0.1 * ((i % 3) - 1 || 1); dy = 0.1; d2 = 0.02; }
        const force = repel / d2;
        p.vx += dx * force * 0.02; p.vy += dy * force * 0.02;
        q.vx -= dx * force * 0.02; q.vy -= dy * force * 0.02;
      }
    }
    for (const { a, b, w } of links) {
      const p = pos[a], q = pos[b];
      const dx = q.x - p.x, dy = q.y - p.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const pull = (d - 70) * 0.004 * w;
      p.vx += dx / d * pull; p.vy += dy / d * pull;
      q.vx -= dx / d * pull; q.vy -= dy / d * pull;
    }
    for (const p of pos) {
      p.vx += (p.anchor.x - p.x) * 0.03; p.vy += (p.anchor.y - p.y) * 0.03;
      const cap = 12 * heat + 0.5;
      p.vx = Math.max(-cap, Math.min(cap, p.vx)); p.vy = Math.max(-cap, Math.min(cap, p.vy));
      p.x += p.vx; p.y += p.vy;
      const ax = p.x - p.anchor.x, ay = p.y - p.anchor.y, far = Math.hypot(ax, ay);
      if (far > reach) { p.x = p.anchor.x + ax / far * reach; p.y = p.anchor.y + ay / far * reach; }
      p.x = Math.max(16, Math.min(width - 16, p.x)); p.y = Math.max(16, Math.min(height - 16, p.y));
      p.vx *= 0.6; p.vy *= 0.6;
    }
  }
  return new Map(nodes.map((node, i) => [node.id, { x: pos[i].x, y: pos[i].y }]));
}
