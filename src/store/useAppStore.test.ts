import { describe, expect, it } from 'vitest';
import { sanitizePersisted } from './useAppStore';

const defaults = { position: null, size: 300, opacity: 1, greetingEnabled: true };

describe('восстановление настроек из localStorage', () => {
  it('сохраняет корректные значения', () => {
    const saved = { position: { x: 10, y: 20 }, size: 240, opacity: 0.6, greetingEnabled: false };
    expect(sanitizePersisted(saved, defaults)).toEqual(saved);
  });
  it('заменяет испорченные значения значениями по умолчанию', () => {
    expect(sanitizePersisted({ position: { x: 'a', y: 5 }, size: 'abc', opacity: null, greetingEnabled: 'yes' }, defaults)).toEqual(defaults);
  });
  it('ограничивает размер и прозрачность допустимым диапазоном', () => {
    expect(sanitizePersisted({ size: 9000, opacity: 0 }, defaults)).toMatchObject({ size: 420, opacity: 0.4 });
  });
  it('переживает пустые и чужие данные', () => {
    expect(sanitizePersisted(null, defaults)).toEqual(defaults);
    expect(sanitizePersisted('мусор', defaults)).toEqual(defaults);
  });
});
