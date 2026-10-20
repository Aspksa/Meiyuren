import { describe, expect, it } from 'vitest';
import { boundPosition, clamp, startingPosition } from './position';

describe('позиция аватара', () => {
  it('ограничивает координаты границами окна', () => {
    expect(boundPosition({ x: -15, y: 1500 }, 200, 900, 600)).toEqual({ x: 0, y: 400 });
  });
  it('не уходит в отрицательные координаты, если окно меньше аватара', () => {
    expect(boundPosition({ x: 90, y: 50 }, 260, 200, 180)).toEqual({ x: 0, y: 0 });
  });
  it('на узком экране ставит аватар в левый нижний угол с отступом', () => {
    expect(startingPosition(200, 1000, 700)).toEqual({ x: 28, y: 468 });
  });
  it('на широком экране ставит аватар справа от текста, левее панели чата', () => {
    expect(startingPosition(300, 1440, 900)).toEqual({ x: 700, y: 340 });
  });
  it('clamp корректен для значений внутри диапазона', () => {
    expect(clamp(4, 1, 10)).toBe(4);
  });
});
