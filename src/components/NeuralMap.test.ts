import { describe, expect, it } from 'vitest';
import { BRAIN_SIGNS, arc, constellation } from './NeuralMap';

describe('constellation', () => {
  it('joins every star of a brain with the shortest lines', () => {
    const points = [{ id: 'a', x: 0, y: 0 }, { id: 'b', x: 10, y: 0 }, { id: 'c', x: 100, y: 0 }, { id: 'd', x: 12, y: 3 }];
    const lines = constellation(points);
    expect(lines).toHaveLength(points.length - 1);
    const keys = lines.map(l => [...l].sort().join('-')).sort();
    expect(keys).toEqual(['a-b', 'b-d', 'c-d']);
  });

  it('draws nothing for a lonely fact', () => {
    expect(constellation([{ id: 'a', x: 1, y: 1 }])).toEqual([]);
  });

  it('gives every brain its own sign', () => {
    expect(new Set(Object.values(BRAIN_SIGNS)).size).toBe(8);
  });
});

describe('arc', () => {
  it('bends to the chosen side and ends at the target', () => {
    expect(arc({ x: 0, y: 0 }, { x: 100, y: 0 }, 0.1, 1)).toBe('M0,0 Q50,10 100,0');
    expect(arc({ x: 0, y: 0 }, { x: 100, y: 0 }, 0.1, -1)).toBe('M0,0 Q50,-10 100,0');
  });
});
