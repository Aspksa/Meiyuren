import { useEffect } from 'react';
import { Avatar } from './components/Avatar';
import { ChatPanel } from './components/ChatPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { useAppStore } from './store/useAppStore';

const interactions = [
  { symbol: '↖', title: 'Нажми', description: 'Левая кнопка — откроется уютный чат.', marker: '01' },
  { symbol: '✣', title: 'Перемести', description: 'Зажми и перетащи в любое место экрана.', marker: '02' },
  { symbol: '⚙', title: 'Настрой', description: 'Правая кнопка — размер и параметры.', marker: '03' },
];

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
        <a href="#home" className="brand" aria-label="Meiyuren — на главную">
          <span className="brand__crest">✿</span>
          <span>MEIYUREN<small>Твоя маленькая магия</small></span>
        </a>
        <nav className="site-nav" aria-label="Навигация">
          <a href="#about">О Мэйюрэн</a>
          <a href="#controls">Управление</a>
        </nav>
        <button type="button" className="header-action" onClick={openChat}>
          <span className="status-dot" aria-hidden="true" />
          Поговорить <span aria-hidden="true">↗</span>
        </button>
      </header>

      <main id="home">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero__constellation" aria-hidden="true">
            <span className="hero__star hero__star--a">✦</span>
            <span className="hero__star hero__star--b">✧</span>
            <span className="hero__star hero__star--c">✦</span>
            <span className="hero__orbit" />
            <span className="hero__orbit hero__orbit--inner" />
            <span className="hero__insignia">九<br />尾</span>
          </div>
          <div className="hero__content">
            <div className="hero__eyebrow"><span className="hero__line" /> ДОБРО ПОЖАЛОВАТЬ В МИР МЭЙЮРЭН</div>
            <h1 id="hero-title">Здесь живёт<br /><em>немного магии.</em></h1>
            <p className="hero__description">
              Познакомься с Мэйюрэн — очаровательной девятихвостой спутницей.
              Она всегда рядом, готова поболтать и украсить твой день.
            </p>
            <div className="hero__buttons">
              <button className="button button--primary" type="button" onClick={openChat}>
                Начать разговор <span aria-hidden="true">↗</span>
              </button>
              <button className="button button--secondary" type="button" onClick={() => openSettings({ x: window.innerWidth / 2 - 150, y: 110 })}>
                Настроить аватар <span aria-hidden="true">⚙</span>
              </button>
            </div>
            <div className="hero__signature" id="about">
              <span className="hero__signature-mark">❀</span>
              <div><strong>Мэйюрэн</strong><span>Маленькая кицунэ с большим сердцем</span></div>
            </div>
          </div>
          <div className="hero__floating-label" aria-hidden="true">
            <span className="hero__floating-label-dot">✧</span>
            <div><strong>ВАША СПУТНИЦА</strong><small>Потяни за аватар, чтобы переместить</small></div>
          </div>
          <div className="hero__side-text" aria-hidden="true">九尾狐 · ТЕПЛО И ВОЛШЕБСТВО</div>
        </section>

        <section className="control-section" id="controls" aria-labelledby="controls-title">
          <div className="control-section__heading">
            <span className="eyebrow-small">ПРОСТО И УДОБНО</span>
            <h2 id="controls-title">Три способа <em>сказать привет</em></h2>
            <p>Всё управление — буквально на кончиках пальцев.</p>
          </div>
          <div className="control-grid">
            {interactions.map((item) => (
              <article className="control-card" key={item.marker}>
                <span className="control-card__index">{item.marker} / 03</span>
                <div className="control-card__symbol" aria-hidden="true">{item.symbol}</div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <div className="control-card__bottom" aria-hidden="true">✦</div>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <span>✦ MEIYUREN © 2026</span>
        <span>Создано с любовью к маленьким чудесам</span>
        <span className="site-footer__version">v0.2 · интерактивный аватар</span>
      </footer>

      <Avatar />
      <ChatPanel />
      <SettingsPanel />
    </div>
  );
}
