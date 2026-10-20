import { useCallback, useEffect, useState } from 'react';
import { getUpdateStatus, updateAction } from '../services/updates';
import type { UpdateStatus } from '../services/updates';

type Confirmation = 'apply' | 'rollback' | null;

export function UpdatePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Confirmation>(null);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');

  const check = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError('');
    try {
      const data = await getUpdateStatus();
      if (!signal?.aborted) setStatus(data);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Ошибка проверки');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void check(controller.signal);
    return () => controller.abort();
  }, [open, check]);

  if (!open) return null;

  async function proceed() {
    if (!confirm || busy) return;
    setBusy(true);
    setError('');
    setResult('');
    try {
      const action = confirm;
      const response = await updateAction(action, action === 'apply' ? status?.remoteSha ?? undefined : undefined);
      setResult(response.message);
      setConfirm(null);
      await check();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка установки');
    } finally {
      setBusy(false);
    }
  }

  const short = (sha: string | null | undefined) => sha ? sha.slice(0, 8) : '—';
  const ciLabel = {
    success: 'Пройдены',
    failed: 'Не пройдены',
    pending: 'Выполняются',
    missing: 'Нет результатов',
    unknown: 'Не проверены',
  }[status?.ci ?? 'unknown'];

  return (
    <section className="updater-panel" role="dialog" aria-label="Обновления Meiyuren">
      <header className="updater-panel__header">
        <div className="updater-panel__emblem"><img src={`${import.meta.env.BASE_URL}assets/icons/update.svg`} alt="" /></div>
        <div><span className="updater-panel__eyebrow">СИСТЕМА ОБНОВЛЕНИЙ</span><h2>Новая магия</h2></div>
        <button type="button" className="updater-panel__close" aria-label="Закрыть обновления" onClick={onClose}>×</button>
      </header>
      <div className="updater-panel__body">
        <p className="updater-panel__intro">Проверка новых версий напрямую из официального репозитория Meiyuren на GitHub.</p>
        <div className="updater-panel__version-grid">
          <div><span>Установлено</span><strong>{short(status?.installedSha)}</strong></div>
          <div><span>На GitHub</span><strong>{short(status?.remoteSha)}</strong></div>
        </div>
        <div className="updater-panel__ci">
          <span className={`updater-panel__signal${status?.ci === 'success' ? ' updater-panel__signal--ok' : ''}`} />
          <span>Проверки CI</span><strong>{ciLabel}</strong>
        </div>
        {status?.message && <p className="updater-panel__message">{status.message}</p>}
        {error && <p className="updater-panel__error" role="alert">{error}</p>}
        {result && <p className="updater-panel__success" role="status">{result}</p>}
        {confirm && (
          <div className="updater-panel__confirm">
            <strong>{confirm === 'apply' ? 'Установить обновление?' : 'Вернуться к прошлой версии?'}</strong>
            <p>{confirm === 'apply'
              ? 'Будет выполнено безопасное fast-forward обновление после успешных проверок GitHub CI. Сохраните свои несохранённые данные в браузере.'
              : 'Будет восстановлен предыдущий коммит. Несохранённые изменения в Git блокируют откат.'}</p>
            <div className="updater-panel__buttons">
              <button type="button" onClick={() => setConfirm(null)} disabled={busy}>Отмена</button>
              <button type="button" className="updater-panel__primary" onClick={() => void proceed()} disabled={busy}>{busy ? 'Выполняется…' : 'Подтвердить'}</button>
            </div>
          </div>
        )}
        {!confirm && (
          <div className="updater-panel__buttons">
            <button type="button" onClick={() => void check()} disabled={loading || busy}>{loading ? 'Проверяю…' : '↻ Проверить'}</button>
            <button type="button" className="updater-panel__primary" disabled={!status?.canApply || busy || loading} onClick={() => setConfirm('apply')}>Установить</button>
            {status?.canRollback && <button type="button" onClick={() => setConfirm('rollback')} disabled={busy || loading}>↶ Откатить</button>}
          </div>
        )}
        <div className="updater-panel__foot">
          <a href="https://github.com/Aspksa/Meiyuren" target="_blank" rel="noopener noreferrer">Исходный код на GitHub ↗</a>
          <p>Автоматическая установка доступна только для чистой Git-копии в ветке main с успешной CI. После обновления перезапустите приложение. Если изменились зависимости, выполните <code>npm install</code>.</p>
        </div>
      </div>
    </section>
  );
}
