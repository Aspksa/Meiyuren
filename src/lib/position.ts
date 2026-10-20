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

export function startingPosition(size: number, width: number, height: number): Point {
  return boundPosition({ x: 28, y: height - size - 32 }, size, width, height);
}
