export type UpdateStatus = {
  mode: 'git' | 'archive';
  installedSha: string | null;
  installedVersion: string | null;
  remoteSha: string | null;
  remoteVersion: string | null;
  hasUpdate: boolean;
  canApply: boolean;
  ci: 'success' | 'failed' | 'pending' | 'missing' | 'unknown';
  canRollback: boolean;
  message: string;
};

export type UpdateActionResult = { success: boolean; message: string; installedSha: string };

export async function getUpdateStatus(): Promise<UpdateStatus> {
  const response = await fetch('/api/updates/status', { cache: 'no-store' });
  if (!response.ok) {
    if (response.status === 404) throw new Error('Модуль обновлений доступен при локальном запуске через Meiyuren.cmd или npm run dev.');
    throw new Error((await response.json().catch(() => null))?.message ?? 'Не удалось проверить обновления.');
  }
  return response.json() as Promise<UpdateStatus>;
}

export async function updateAction(action: 'apply' | 'rollback', expectedSha?: string): Promise<UpdateActionResult> {
  const response = await fetch(`/api/updates/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Meiyuren-Confirm': 'yes' },
    credentials: 'same-origin',
    body: JSON.stringify({ confirm: action, expectedSha }),
  });
  const data: { message?: string; success?: boolean; installedSha?: string } | null = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.message ?? 'Операция обновления не выполнена.');
  return { success: data?.success === true, message: data?.message ?? '', installedSha: data?.installedSha ?? '' };
}
