import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { clamp } from '../lib/position';
import type { Point } from '../lib/position';

export type Message = {
  id: string;
  role: 'assistant' | 'user';
  text: string;
  sentAt: number;
};

export const SIZE_MIN = 160;
export const SIZE_MAX = 420;
export const SIZE_DEFAULT = 300;
export const OPACITY_MIN = 0.4;
export const OPACITY_MAX = 1;

type PersistedState = {
  position: Point | null;
  size: number;
  opacity: number;
  greetingEnabled: boolean;
};

type AppState = PersistedState & {
  chatOpen: boolean;
  settingsOpen: boolean;
  settingsAnchor: Point;
  messages: Message[];
  setPosition: (position: Point) => void;
  setSize: (size: number) => void;
  setOpacity: (opacity: number) => void;
  setGreetingEnabled: (enabled: boolean) => void;
  openChat: () => void;
  closeChat: () => void;
  openSettings: (anchor: Point) => void;
  closeSettings: () => void;
  resetPosition: () => void;
  addMessage: (role: Message['role'], text: string) => string;
  clearChat: () => void;
};

let nextMessageId = 0;
function message(role: Message['role'], text: string): Message {
  nextMessageId += 1;
  return { id: `${Date.now()}-${nextMessageId}`, role, text, sentAt: Date.now() };
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

// Данные из localStorage могут быть испорчены вручную или старой версией:
// пропускаем только корректные значения, остальное берём по умолчанию.
export function sanitizePersisted(raw: unknown, defaults: PersistedState): PersistedState {
  const data = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const pos = data.position as Record<string, unknown> | null | undefined;
  return {
    position: pos && isFiniteNumber(pos.x) && isFiniteNumber(pos.y) ? { x: pos.x, y: pos.y } : null,
    size: isFiniteNumber(data.size) ? clamp(data.size, SIZE_MIN, SIZE_MAX) : defaults.size,
    opacity: isFiniteNumber(data.opacity) ? clamp(data.opacity, OPACITY_MIN, OPACITY_MAX) : defaults.opacity,
    greetingEnabled: typeof data.greetingEnabled === 'boolean' ? data.greetingEnabled : defaults.greetingEnabled,
  };
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      position: null,
      size: SIZE_DEFAULT,
      opacity: 1,
      greetingEnabled: true,
      chatOpen: false,
      settingsOpen: false,
      settingsAnchor: { x: 60, y: 70 },
      messages: [],
      setPosition: (position) => {
        if (isFiniteNumber(position.x) && isFiniteNumber(position.y)) set({ position });
      },
      setSize: (size) => {
        if (isFiniteNumber(size)) set({ size: clamp(size, SIZE_MIN, SIZE_MAX) });
      },
      setOpacity: (opacity) => {
        if (isFiniteNumber(opacity)) set({ opacity: clamp(opacity, OPACITY_MIN, OPACITY_MAX) });
      },
      setGreetingEnabled: (greetingEnabled) => set({ greetingEnabled }),
      openChat: () =>
        set((state) => ({
          chatOpen: true,
          settingsOpen: false,
          messages:
            state.messages.length === 0 && state.greetingEnabled
              ? [message('assistant', 'Привет! Я Мэйюрэн. Рада тебя видеть ✨ Чем займёмся?')]
              : state.messages,
        })),
      closeChat: () => set({ chatOpen: false }),
      openSettings: (settingsAnchor) => set({ settingsOpen: true, settingsAnchor }),
      closeSettings: () => set({ settingsOpen: false }),
      resetPosition: () => set({ position: null }),
      addMessage: (role, text) => {
        const item = message(role, text);
        set((state) => ({ messages: [...state.messages, item] }));
        return item.id;
      },
      clearChat: () => set({ messages: [] }),
    }),
    {
      name: 'meiyuren-settings-v1',
      version: 1,
      partialize: (state): PersistedState => ({
        position: state.position,
        size: state.size,
        opacity: state.opacity,
        greetingEnabled: state.greetingEnabled,
      }),
      migrate: (persisted) => persisted as PersistedState,
      merge: (persisted, current) => ({ ...current, ...sanitizePersisted(persisted, current) }),
    },
  ),
);
