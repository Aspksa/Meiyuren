export type AvatarOption = { id: string; label: string };

// Позы Мэйюрэн. Картинки лежат в public/assets/avatar/poses/<id>.webp,
// миниатюры для меню настроек — в <id>-thumb.webp.
export const AVATARS: readonly AvatarOption[] = [
  { id: 'bow', label: 'Поклон' },
  { id: 'welcome', label: 'Приветствие' },
  { id: 'invite', label: 'Приглашение' },
  { id: 'heart', label: 'Рука на сердце' },
  { id: 'kneel', label: 'На колене' },
  { id: 'pray', label: 'Молитва' },
  { id: 'shy', label: 'Смущение' },
  { id: 'sit', label: 'Сидит' },
  { id: 'bow-side', label: 'Реверанс' },
  { id: 'sleep', label: 'Сон' },
];

export const DEFAULT_AVATAR_ID = AVATARS[0].id;

export function isAvatarId(value: unknown): value is string {
  return typeof value === 'string' && AVATARS.some((item) => item.id === value);
}

export function avatarUrl(id: string, thumb = false): string {
  const safeId = isAvatarId(id) ? id : DEFAULT_AVATAR_ID;
  return `${import.meta.env.BASE_URL}assets/avatar/poses/${safeId}${thumb ? '-thumb' : ''}.webp`;
}
