import { useEffect, useState } from 'react';
import { IconSidebar } from './components/IconSidebar';
import { UpdatePanel } from './components/UpdatePanel';
import { CloudSettingsPanel } from './components/CloudSettingsPanel';
import { Avatar } from './components/Avatar';
import { ChatPanel } from './components/ChatPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { useAppStore } from './store/useAppStore';
import { getCloudSettings } from './services/cloudApi';

export default function App() {
  const openChat = useAppStore((s) => s.openChat);
  const openSettings = useAppStore((s) => s.openSettings);
  const [updatesOpen, setUpdatesOpen] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const chatOpen = useAppStore((s) => s.chatOpen);
  const settingsOpen = useAppStore((s) => s.settingsOpen);

  // Когда Cloud.ru настроен, сразу открываем чат: при запуске и после закрытия панели Cloud.ru.
  useEffect(() => {
    if (cloudOpen) return;
    const controller = new AbortController();
    void getCloudSettings(controller.signal).then(state => {
      if (controller.signal.aborted) return;
      if (state.hasKey && state.enabled && state.model) useAppStore.getState().openChat();
    }).catch(() => { /* Сервер недоступен: остаётся пустая главная. */ });
    return () => controller.abort();
  }, [cloudOpen]);

  // Панели открываются на одном месте рядом с меню, поэтому одновременно видна только одна.
  useEffect(() => {
    if (chatOpen || settingsOpen) { setUpdatesOpen(false); setCloudOpen(false); }
  }, [chatOpen, settingsOpen]);

  // Escape слушаем на window: так он работает, даже когда фокус на body.
  // Сначала закрываются настройки (они поверх), затем чат.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      const state = useAppStore.getState();
      if (cloudOpen) { setCloudOpen(false); return; }
      if (updatesOpen) { setUpdatesOpen(false); return; }
      if (state.settingsOpen) state.closeSettings();
      else if (state.chatOpen) state.closeChat();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [updatesOpen, cloudOpen]);

  return (
    <div className="site">
      <div className="ambient ambient--one" aria-hidden="true" />
      <div className="ambient ambient--two" aria-hidden="true" />
      <div className="sparks" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>

      <main id="home" className="stage" aria-label="Meiyuren" />

      <IconSidebar
        updatesOpen={updatesOpen}
        onHome={() => { setUpdatesOpen(false); setCloudOpen(false); useAppStore.getState().closeSettings(); useAppStore.getState().closeChat(); }}
        onChat={() => { setUpdatesOpen(false); setCloudOpen(false); if (chatOpen) useAppStore.getState().closeChat(); else openChat(); }}
        onSettings={() => { setUpdatesOpen(false); setCloudOpen(false); if (settingsOpen) useAppStore.getState().closeSettings(); else openSettings({ x: 110, y: 120 }); }}
        chatOpen={chatOpen}
        settingsOpen={settingsOpen}
        onUpdates={() => { useAppStore.getState().closeSettings(); useAppStore.getState().closeChat(); setCloudOpen(false); setUpdatesOpen((value) => !value); }}
        cloudOpen={cloudOpen}
        onCloud={() => { useAppStore.getState().closeSettings(); useAppStore.getState().closeChat(); setUpdatesOpen(false); setCloudOpen((value) => !value); }}
      />
      <UpdatePanel open={updatesOpen} onClose={() => setUpdatesOpen(false)} />
      <CloudSettingsPanel open={cloudOpen} onClose={() => setCloudOpen(false)} />
      <Avatar />
      <ChatPanel />
      <SettingsPanel />
    </div>
  );
}
