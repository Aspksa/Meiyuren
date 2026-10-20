export type Point = { x: number; y: number };

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, max));
}

export function boundPosition(position: Point, size: number, width: number, height: number): Point {
  return {
    x: clamp(position.x, 0, Math.max(0, width - size)),
    y: clamp(position.y, 0, Math.max(0, height - size)),
  };
}

// Ширина панели чата с отступом: на широком экране аватар стоит справа от текста, но не под чатом.
const CHAT_GUTTER = 440;
export const WIDE_LAYOUT = 1100;

export function startingPosition(size: number, width: number, height: number): Point {
  const point = width >= WIDE_LAYOUT
    ? { x: width - size - CHAT_GUTTER, y: (height - size) / 2 + 40 }
    : { x: 28, y: height - size - 32 };
  return boundPosition(point, size, width, height);
}
