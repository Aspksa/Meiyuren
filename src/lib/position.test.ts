import { describe, expect, it } from 'vitest';
import { boundPosition, clamp, startingPosition } from './position';

describe('позиция аватара', () => {
  it('ограничивает координаты границами окна', () => {
    expect(boundPosition({ x: -15, y: 1500 }, 200, 900, 600)).toEqual({ x: 0, y: 400 });
  });
  it('не уходит в отрицательные координаты, если окно меньше аватара', () => {
    expect(boundPosition({ x: 90, y: 50 }, 260, 200, 180)).toEqual({ x: 0, y: 0 });
  });
  it('ставит аватар справа на широком экране', () => {
    expect(startingPosition(300, 1200, 800)).toEqual({ x: 816, y: 168 });
  });
  it('ставит аватар по центру ближе к низу на телефоне', () => {
    expect(startingPosition(260, 390, 844)).toEqual({ x: 65, y: 542 });
  });
  it('clamp корректен для значений внутри диапазона', () => {
    expect(clamp(4, 1, 10)).toBe(4);
  });
});
