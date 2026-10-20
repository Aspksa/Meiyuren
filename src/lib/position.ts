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
  // На широких экранах аватар находится у декоративного круга справа.
  if (width >= 800) {
    return boundPosition({
      x: width - size - Math.max(35, Math.min(width * 0.07, 125)),
      y: Math.max(110, Math.min(height * 0.21, 200)),
    }, size, width, height);
  }
  // На телефоне аватар размещён ближе к нижней части экрана.
  return boundPosition({
    x: (width - size) / 2,
    y: height - size - 42,
  }, size, width, height);
}
