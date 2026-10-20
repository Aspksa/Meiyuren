import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Point } from '../lib/position';

export type Message = {
  id: string;
  role: 'assistant' | 'user';
  text: string;
  sentAt: number;
};

type AppState = {
  position: Point | null;
  size: number;
  opacity: number;
  greetingEnabled: boolean;
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
  addMessage: (role: Message['role'], text: string) => void;
  clearChat: () => void;
};

let nextMessageId = 0;
function message(role: Message['role'], text: string): Message {
  nextMessageId += 1;
  return { id: `${Date.now()}-${nextMessageId}`, role, text, sentAt: Date.now() };
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      position: null,
      size: 280,
      opacity: 1,
      greetingEnabled: true,
      chatOpen: false,
      settingsOpen: false,
      settingsAnchor: { x: 60, y: 70 },
      messages: [],
      setPosition: (position) => set({ position }),
      setSize: (size) => set({ size }),
      setOpacity: (opacity) => set({ opacity }),
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
      addMessage: (role, text) =>
        set((state) => ({ messages: [...state.messages, message(role, text)] })),
      clearChat: () => set({ messages: [] }),
    }),
    {
      name: 'meiyuren-settings-v1',
      partialize: (state) => ({
        position: state.position,
        size: state.size,
        opacity: state.opacity,
        greetingEnabled: state.greetingEnabled,
      }),
    },
  ),
);
