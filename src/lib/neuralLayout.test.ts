import { describe, expect, it } from 'vitest';
import { brainAnchor, layoutGraph } from './neuralLayout';
import { plural } from './plural';

describe('layoutGraph', () => {
  const nodes = [
    { id: 'a', brain: 'projects' }, { id: 'b', brain: 'projects' },
    { id: 'c', brain: 'goals' }, { id: 'd', brain: 'habits' },
  ];

  it('is deterministic and keeps every node inside the canvas', () => {
    const first = layoutGraph(nodes, [{ source: 'a', target: 'c', weight: 0.6 }], 800, 560);
    const second = layoutGraph(nodes, [{ source: 'a', target: 'c', weight: 0.6 }], 800, 560);
    expect([...first.entries()]).toEqual([...second.entries()]);
    for (const p of first.values()) {
      expect(p.x).toBeGreaterThanOrEqual(16); expect(p.x).toBeLessThanOrEqual(784);
      expect(p.y).toBeGreaterThanOrEqual(16); expect(p.y).toBeLessThanOrEqual(544);
    }
  });

  it('keeps facts near their own brain', () => {
    const placed = layoutGraph(nodes, [], 800, 560);
    const anchor = brainAnchor('goals', 800, 560);
    const c = placed.get('c')!;
    expect(Math.hypot(c.x - anchor.x, c.y - anchor.y)).toBeLessThanOrEqual(56.01);
  });

  it('keeps linked facts inside their brain cloud', () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: `n${i}`, brain: i % 2 ? 'goals' : 'habits' }));
    const edges = many.slice(1).map((n, i) => ({ source: many[i].id, target: n.id, weight: 1 }));
    const placed = layoutGraph(many, edges, 800, 560);
    for (const node of many) {
      const p = placed.get(node.id)!, a = brainAnchor(node.brain, 800, 560);
      expect(Math.hypot(p.x - a.x, p.y - a.y)).toBeLessThanOrEqual(56.01);
    }
  });

  it('ignores edges to unknown nodes', () => {
    expect(layoutGraph(nodes, [{ source: 'a', target: 'zzz', weight: 1 }], 800, 560).size).toBe(4);
  });
});

describe('plural', () => {
  it('declines Russian counts', () => {
    expect(plural(1, 'связь', 'связи', 'связей')).toBe('1 связь');
    expect(plural(3, 'связь', 'связи', 'связей')).toBe('3 связи');
    expect(plural(11, 'связь', 'связи', 'связей')).toBe('11 связей');
    expect(plural(21, 'связь', 'связи', 'связей')).toBe('21 связь');
  });
});
