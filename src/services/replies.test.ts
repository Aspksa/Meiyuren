import { describe, expect, it } from 'vitest';
import { getDemoReply } from './replies';

describe('демо-ответы', () => {
  it('знает своё имя', () => {
    expect(getDemoReply('Кто ты?')).toContain('Мэйюрэн');
  });
  it('имеет универсальный ответ без сетевого API', () => {
    expect(getDemoReply('123xyz')).toContain('демонстрационные');
  });
});
