import { useEffect } from 'react';
import { Avatar } from './components/Avatar';
import { ChatPanel } from './components/ChatPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { useAppStore } from './store/useAppStore';

export default function App() {
  const openChat = useAppStore((s) => s.openChat);
  const openSettings = useAppStore((s) => s.openSettings);

  // Escape слушаем на window: так он работает, даже когда фокус на body.
  // Сначала закрываются настройки (они поверх), затем чат.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      const state = useAppStore.getState();
      if (state.settingsOpen) state.closeSettings();
      else if (state.chatOpen) state.closeChat();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div className="site">
      <div className="ambient ambient--one" aria-hidden="true" />
      <div className="ambient ambient--two" aria-hidden="true" />
      <div className="sparks" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
      <header className="site-header">
        <a href="#" className="brand" aria-label="Meiyuren — главная" onClick={(event) => event.preventDefault()}>
          <span className="brand__crest">狐</span>
          <span>MEIYUREN<small>virtual companion</small></span>
        </a>
        <span className="site-header__status"><i /> Версия 0.2</span>
      </header>
      <main className="hero">
        <div className="hero__eyebrow"><span className="hero__line" /> ДОБРО ПОЖАЛОВАТЬ В МИР МЭЙЮРЭН</div>
        <h1>Твоя спутница.<br /><em>Всегда рядом.</em></h1>
        <p className="hero__description">
          Девятихвостая кицунэ в золотых одеждах поселилась на этой странице.
          Познакомься с ней: поговори, перетащи в удобное место
          и настрой всё под себя.
        </p>
        <div className="hero__buttons">
          <button className="button button--primary" type="button" onClick={openChat}>Начать разговор <span>↗</span></button>
          <button className="button button--secondary" type="button" onClick={() => openSettings({ x: window.innerWidth / 2 - 150, y: 110 })}>Настроить аватар <span>⚙</span></button>
        </div>
        <div className="guide">
          <p className="guide__title">ПОПРОБУЙ ВЗАИМОДЕЙСТВОВАТЬ</p>
          <div className="guide__items">
            <div className="guide__item"><span className="guide__symbol">↖</span><div><strong>Левый клик</strong><small>Открыть чат</small></div></div>
            <div className="guide__item"><span className="guide__symbol">⋮</span><div><strong>Правый клик</strong><small>Настройки</small></div></div>
            <div className="guide__item"><span className="guide__symbol">✥</span><div><strong>Перетащи</strong><small>Измени положение</small></div></div>
          </div>
        </div>
      </main>
      <div className="vertical-caption" aria-hidden="true">狐 · НЕМНОГО ВОЛШЕБСТВА КАЖДЫЙ ДЕНЬ</div>
      <footer className="site-footer"><span>✦ MEIYUREN © 2026</span><span>С любовью к маленьким чудесам</span></footer>
      <Avatar />
      <ChatPanel />
      <SettingsPanel />
    </div>
  );
}
