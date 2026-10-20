import { useEffect, useState } from 'react';
import { MemoryEditor } from './MemoryEditor';
import { AVATARS, avatarUrl } from '../lib/avatars';
import { OPACITY_MAX, OPACITY_MIN, SIZE_MAX, SIZE_MIN, useAppStore } from '../store/useAppStore';

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
  const avatarId = useAppStore((s) => s.avatarId);
  const setAvatarId = useAppStore((s) => s.setAvatarId);
  const [viewport, setViewport] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));

  useEffect(() => {
    if (!open) return;
    const onResize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open]);

  if (!open) return null;
  const width = Math.min(320, viewport.width - 24);
  const left = Math.max(12, Math.min(anchor.x, viewport.width - width - 12));
  const top = Math.max(12, Math.min(anchor.y, viewport.height - Math.min(560, viewport.height - 24) - 12));

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
        <fieldset className="setting avatar-picker">
          <legend className="setting__heading"><span>Образ</span><output>{AVATARS.find((item) => item.id === avatarId)?.label}</output></legend>
          <div className="avatar-picker__grid" role="radiogroup" aria-label="Выбор аватара">
            {AVATARS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={item.id === avatarId}
                aria-label={item.label}
                title={item.label}
                className={`avatar-picker__item ${item.id === avatarId ? 'avatar-picker__item--active' : ''}`}
                onClick={() => setAvatarId(item.id)}
              >
                <img src={avatarUrl(item.id, true)} alt="" loading="lazy" draggable={false} />
              </button>
            ))}
          </div>
        </fieldset>
        <label className="setting">
          <span className="setting__heading"><span>Размер аватара</span><output>{size} px</output></span>
          <input type="range" min={SIZE_MIN} max={SIZE_MAX} step="10" value={size} onChange={(event) => setSize(Number(event.target.value))} />
        </label>
        <label className="setting">
          <span className="setting__heading"><span>Прозрачность</span><output>{Math.round(opacity * 100)}%</output></span>
          <input type="range" min={OPACITY_MIN} max={OPACITY_MAX} step="0.05" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} />
        </label>
        <label className="setting setting--toggle">
          <span><strong>Приветствие в чате</strong><small>Показывать при первом открытии</small></span>
          <input type="checkbox" checked={greeting} onChange={(event) => setGreeting(event.target.checked)} />
        </label>
        <div className="setting-actions">
          <button type="button" onClick={() => { resetPosition(); close(); }}>Сбросить позицию</button>
        </div>
        <MemoryEditor active={open} />
        <p className="settings-panel__hint">Настройки и положение сохраняются в браузере, история и заметки — локально в SQLite.</p>
      </div>
    </aside>
  );
}
