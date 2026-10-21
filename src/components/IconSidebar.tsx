import type { ReactNode } from 'react';

type IconName = 'home' | 'chat' | 'settings' | 'github' | 'network';

function Icon({ name }: { name: IconName }) {
  const common = { width: 23, height: 23, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  if (name === 'home') return <svg {...common} aria-hidden="true"><path d="m3.5 10 8.5-7 8.5 7V20a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1Z" /></svg>;
  if (name === 'chat') return <svg {...common} aria-hidden="true"><path d="M20 11.5c0 4.3-3.5 7.5-8 7.5-1.2 0-2.4-.2-3.5-.7L4 20l1.4-4C4.5 14.7 4 13.2 4 11.5 4 7.3 7.6 4 12 4s8 3.3 8 7.5Z"/><path d="M8 11.5h8" /></svg>;
  if (name === 'network') return <svg {...common} aria-hidden="true"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="12" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="12" cy="19" r="2"/><path d="M10.6 6.5 6.4 10.5m7-4 4.2 4m-11.2 3 4.2 4m7-4-4.2 4M7 12h10"/></svg>;
  if (name === 'settings') return <svg {...common} aria-hidden="true"><path d="m10 3-.5 2.1a7 7 0 0 0-1.7.9l-2-.8L4 9l1.7 1.4a7 7 0 0 0 0 1.8L4 13.6l1.8 3 2-.8c.5.4 1 .7 1.7.9L10 19h4l.5-2.3c.6-.2 1.2-.5 1.7-.9l2 .8 1.8-3-1.7-1.4a7 7 0 0 0 0-1.8L20 9l-1.8-3-2 .8c-.5-.4-1.1-.7-1.7-.9L14 3Z" transform="translate(0 1)"/><circle cx="12" cy="12" r="2.5"/></svg>;
  return <svg {...common} aria-hidden="true"><path d="M9 19c-4 1.2-4-2-5-2.5m10 5v-3a3.4 3.4 0 0 0-.8-2.7c3-.3 6.3-1.4 6.3-7a5.4 5.4 0 0 0-1.5-3.8 5 5 0 0 0-.1-3.8S16 1 14 2.7a14 14 0 0 0-5 0C7 1 5.1 1.2 5.1 1.2a5 5 0 0 0-.1 3.8A5.4 5.4 0 0 0 3.5 9c0 5.6 3.3 6.7 6.3 7a3.3 3.3 0 0 0-.8 2.7v3" /></svg>;
}

function CloudSymbol() {
  return <svg width="25" height="25" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <path d="M8 24a6.5 6.5 0 0 1-1.5-12.8 9 9 0 0 1 17.3 1.8A5.8 5.8 0 0 1 24 24H8Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13 18h6m-3-3v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
  </svg>;
}

function SidebarButton({ label, active = false, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-label={label} aria-pressed={active} title={label} className={`side-nav__button${active ? ' side-nav__button--active' : ''}`} onClick={onClick}>{children}</button>;
}

export function IconSidebar({ onHome, onChat, onSettings, onUpdates, onCloud, onNetwork, chatOpen, settingsOpen, updatesOpen, cloudOpen, networkOpen }: {
  onHome: () => void;
  onChat: () => void;
  onSettings: () => void;
  onUpdates: () => void;
  onCloud: () => void;
  onNetwork: () => void;
  networkOpen: boolean;
  chatOpen: boolean;
  settingsOpen: boolean;
  updatesOpen: boolean;
  cloudOpen: boolean;
}) {
  return (
    <nav className="side-nav" aria-label="Главное меню">
      <div className="side-nav__logo" title="Meiyuren" aria-hidden="true">✿</div>
      <span className="side-nav__line" aria-hidden="true" />
      <SidebarButton label="Главная" onClick={onHome}><Icon name="home" /></SidebarButton>
      <SidebarButton label="Чат" active={chatOpen} onClick={onChat}><Icon name="chat" /></SidebarButton>
      <SidebarButton label="Нейросеть" active={networkOpen} onClick={onNetwork}><Icon name="network" /></SidebarButton>
      <SidebarButton label="Обновления" active={updatesOpen} onClick={onUpdates}>
        <img className="side-nav__update" src={`${import.meta.env.BASE_URL}assets/icons/update.svg`} alt="" aria-hidden="true" />
      </SidebarButton>
      <SidebarButton label="Cloud.ru" active={cloudOpen} onClick={onCloud}><CloudSymbol /></SidebarButton>
      <SidebarButton label="Настройки" active={settingsOpen} onClick={onSettings}><Icon name="settings" /></SidebarButton>
      <span className="side-nav__spacer" aria-hidden="true" />
      <a className="side-nav__button" href="https://github.com/Aspksa/Meiyuren" target="_blank" rel="noopener noreferrer" aria-label="Репозиторий GitHub" title="Репозиторий GitHub"><Icon name="github" /></a>
    </nav>
  );
}
