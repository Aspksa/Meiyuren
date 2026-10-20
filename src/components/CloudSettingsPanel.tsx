import { useEffect, useState } from 'react';
import { deleteCloudKey, getCloudDiagnostics, getCloudModels, getCloudSettings, putCloudKey, putCloudSettings } from '../services/cloudApi';
import { streamMessage } from '../services/chatApi';
import type { CloudDiagnostics } from '../services/cloudApi';

export function CloudSettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [keyInput, setKeyInput] = useState('');
  const [hasKey, setHasKey] = useState(false);
  const [model, setModel] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [diagnostics, setDiagnostics] = useState<CloudDiagnostics | null>(null);
  const [testAnswer, setTestAnswer] = useState('');

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setError('');
    setMessage('');
    setDiagnostics(null);
    setTestAnswer('');
    setModels([]);
    setModelsLoaded(false);
    setKeyInput('');
    setBusy(true);
    void getCloudSettings(controller.signal).then((state) => {
      if (controller.signal.aborted) return;
      setHasKey(state.hasKey);
      setModel(state.model);
      setEnabled(state.enabled);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Ошибка настроек');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [open]);

  async function action(task: () => Promise<string>) {
    setBusy(true);
    setError('');
    setMessage('');
    try { setMessage(await task()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка Cloud.ru'); }
    finally { setBusy(false); }
  }

  if (!open) return null;

  async function saveKey() {
    await action(async () => {
      await putCloudKey(keyInput);
      setKeyInput('');
      setHasKey(true);
      setEnabled(false);
      setModels([]);
      setDiagnostics(null);
      setModelsLoaded(false);
      return 'Ключ сохранён в системном хранилище учётных данных.';
    });
  }

  async function removeKey() {
    if (!window.confirm('Удалить сохранённый ключ Cloud.ru с этого компьютера?')) return;
    await action(async () => {
      await deleteCloudKey();
      setKeyInput('');
      setHasKey(false);
      setEnabled(false);
      setModels([]);
      setModelsLoaded(false);
      return 'Ключ удалён, облачный чат выключен.';
    });
  }

  async function refreshModels() {
    await action(async () => {
      const available = await getCloudModels();
      setModels(available);
      setModelsLoaded(true);
      if (model && !available.includes(model)) setModel('');
      return available.length ? 'Подключение работает. Доступно моделей: ' + available.length : 'Подключение установлено, но доступных моделей не найдено.';
    });
  }

  async function saveSettings(nextEnabled: boolean) {
    await action(async () => {
      await putCloudSettings(model, nextEnabled);
      setEnabled(nextEnabled);
      return nextEnabled ? 'Cloud.ru выбран для ответов Мэйюрэн.' : 'Облачный чат выключен; работают локальные демо-ответы.';
    });
  }

  async function diagnose() {
    await action(async () => {
      const result = await getCloudDiagnostics();
      setDiagnostics(result);
      return result.message || (result.reachable ? 'Связь с Cloud.ru работает.' : 'Нет подключения.');
    });
  }

  async function paidTest() {
    if (!window.confirm('Отправить платный тестовый запрос к выбранной модели Cloud.ru? Тест сохранится в основном чате.')) return;
    await action(async () => {
      setTestAnswer('');
      const result = await streamMessage('Ответь одним словом: привет', crypto.randomUUID(), 'main',
        part => setTestAnswer(value => value + part));
      return 'Тест завершён: ' + result.assistant.text.slice(0, 120);
    });
  }

  const available = model && !models.includes(model) ? [model, ...models] : models;
  const verifiedModel = modelsLoaded && models.includes(model);
  return (
    <section className="cloud-settings" role="dialog" aria-label="Настройки Cloud.ru">
      <header className="cloud-settings__header">
        <span className="cloud-settings__emblem" aria-hidden="true">
          <svg viewBox="0 0 48 48" fill="none" width="35" height="35">
            <path d="M12 35a9 9 0 0 1-1-18 14 14 0 0 1 27 4 7 7 0 0 1-1 14H12Z" stroke="currentColor" strokeWidth="2.1" strokeLinejoin="round"/>
            <path d="M19 27h11m-6-5v10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </span>
        <div><span className="cloud-settings__eyebrow">AI-ПРОВАЙДЕР</span><h2>Cloud.ru</h2></div>
        <button type="button" aria-label="Закрыть Cloud.ru" className="cloud-settings__close" onClick={onClose}>×</button>
      </header>
      <div className="cloud-settings__body">
        <p className="cloud-settings__description">Foundation Models — модели ИИ по API. Ключ хранится в системном хранилище учётных данных, а не в браузере или SQLite.</p>
        <div className="cloud-settings__status">
          <span className={hasKey ? 'cloud-settings__led cloud-settings__led--on' : 'cloud-settings__led'} />
          <span>{hasKey ? 'Ключ сохранён' : 'Ключ не сохранён'}</span>
          <strong>{enabled ? 'Облако активно' : 'Демо-режим'}</strong>
        </div>

        <label className="cloud-settings__label" htmlFor="meiyuren-cloud-key">API-ключ Cloud.ru</label>
        <input id="meiyuren-cloud-key" className="cloud-settings__input" type="password" autoComplete="off"
          spellCheck={false} value={keyInput} placeholder={hasKey ? 'Введите новый ключ для замены' : 'Введите Key Secret'}
          onChange={(event) => setKeyInput(event.target.value)} disabled={busy} maxLength={2048}/>
        <div className="cloud-settings__actions">
          <button type="button" className="cloud-settings__primary" disabled={busy || !keyInput.trim()} onClick={() => void saveKey()}>Сохранить ключ</button>
          {hasKey && <button type="button" disabled={busy} onClick={() => void removeKey()}>Удалить</button>}
        </div>
        <div className="cloud-settings__separator" />
        <div className="cloud-settings__model-title">
          <label className="cloud-settings__label" htmlFor="meiyuren-cloud-model">Модель</label>
          <button type="button" onClick={() => void refreshModels()} disabled={!hasKey || busy}>↻ Получить список</button>
        </div>
        <select id="meiyuren-cloud-model" className="cloud-settings__select" value={model}
          disabled={!hasKey || busy || available.length === 0}
          onChange={(event) => setModel(event.target.value)}>
          <option value="">Выберите модель</option>
          {available.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
        <p className="cloud-settings__hint">Для включения облачного чата сначала загрузите список моделей с текущим ключом и выберите доступную текстовую модель. Модели embedding и audio исключаются.</p>
        <div className="cloud-settings__actions">
          <button type="button" className="cloud-settings__primary" disabled={busy || !hasKey || !verifiedModel} onClick={() => void saveSettings(true)}>Применить модель</button>
          <button type="button" disabled={busy || !enabled} onClick={() => void saveSettings(false)}>Выключить Cloud.ru</button>
        </div>
        <div className="cloud-settings__separator" />
        <p className="cloud-settings__hint">Диагностика проверяет доступность списка моделей и выбранной модели. Она не запускает генерацию и не расходует токены чата.</p>
        <div className="cloud-settings__actions">
          <button type="button" disabled={busy || !hasKey} onClick={() => void diagnose()}>Проверить соединение</button>
          <button type="button" disabled={busy || !enabled || !hasKey}
            onClick={() => void paidTest()}>Тест ответа (платно)</button>
        </div>
        {diagnostics && <div className="cloud-settings__diagnostic" role="status">
          <p>Соединение: {diagnostics.reachable ? 'доступно' : 'не подтверждено'}</p>
          <p>Выбранная модель: {diagnostics.modelAvailable ? 'доступна' : 'не найдена'}</p>
          <p>Моделей: {diagnostics.modelsCount} · Задержка: {diagnostics.latencyMs ?? '—'} мс</p>
        </div>}
        {testAnswer && <p className="cloud-settings__success">Ответ теста: {testAnswer}</p>}
        {error && <p className="cloud-settings__error" role="alert">{error}</p>}
        {message && <p className="cloud-settings__success" role="status">{message}</p>}
        <div className="cloud-settings__footer">
          <p>В облачном режиме сообщения, часть истории и заметка памяти отправляются Cloud.ru. Возможна платная тарификация запросов.</p>
          <a href="https://cloud.ru/docs/foundation-models/ug/topics/quickstart" target="_blank" rel="noopener noreferrer">Как получить ключ Cloud.ru ↗</a>
        </div>
      </div>
    </section>
  );
}
