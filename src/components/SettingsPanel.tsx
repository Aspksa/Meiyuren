import { useAppStore } from '../store/useAppStore';

export function SettingsPanel() {
  const open = useAppStore((s) => s.settingsOpen);
  const anchor = useAppStore((s) => s.settingsAnchor);
  const close = useAppStore((s) => s.closeSettings);
  const size = useAppStore((s) => s.size);
  const setSize = useAppStore((s) => s.setSize);
  const opacity = useAppStore((s) => s.opacity);
  const setOpacity = useAppStore((s) => s.setOpacity);
  const greeting = useAppStore((s) => s.greetingEnabled);
  const setGreeting = useAppStore((s) => s.setGreetingEnabled);
  const resetPosition = useAppStore((s) => s.resetPosition);
  const clearChat = useAppStore((s) => s.clearChat);

  if (!open) return null;
  const width = Math.min(320, window.innerWidth - 24);
  const left = Math.max(12, Math.min(anchor.x, window.innerWidth - width - 12));
  const top = Math.max(12, Math.min(anchor.y, window.innerHeight - Math.min(390, window.innerHeight - 24) - 12));

  return (
    <aside className="settings-panel" role="dialog" aria-label="Настройки аватара" style={{ left, top, width }}>
      <header className="panel-header">
        <span className="panel-header__mark">⚙</span>
        <div>
          <strong>Настройки</strong>
          <span className="panel-header__sub">Персонализация аватара</span>
        </div>
        <button type="button" onClick={close} className="icon-button panel-header__close" aria-label="Закрыть настройки">×</button>
      </header>
      <div className="settings-panel__body">
        <label className="setting">
          <span className="setting__heading"><span>Размер аватара</span><output>{size} px</output></span>
          <input type="range" min="160" max="420" step="10" value={size} onChange={(event) => setSize(Number(event.target.value))} />
        </label>
        <label className="setting">
          <span className="setting__heading"><span>Прозрачность</span><output>{Math.round(opacity * 100)}%</output></span>
          <input type="range" min="0.4" max="1" step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} />
        </label>
        <label className="setting setting--toggle">
          <span><strong>Приветствие в чате</strong><small>Показывать при первом открытии</small></span>
          <input type="checkbox" checked={greeting} onChange={(event) => setGreeting(event.target.checked)} />
        </label>
        <div className="setting-actions">
          <button type="button" onClick={() => { resetPosition(); close(); }}>Сбросить позицию</button>
          <button type="button" onClick={clearChat}>Очистить чат</button>
        </div>
        <p className="settings-panel__hint">Настройки и положение сохраняются только в этом браузере.</p>
      </div>
    </aside>
  );
}
