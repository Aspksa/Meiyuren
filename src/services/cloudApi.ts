export type CloudSettings = { hasKey: boolean; model: string; enabled: boolean };

async function parseResponse<T>(response: Response): Promise<T> {
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    throw new Error(typeof detail === 'string' ? detail : 'Ошибка Cloud.ru. Проверьте соединение с Python.');
  }
  return data as T;
}

export async function getCloudSettings(signal?: AbortSignal): Promise<CloudSettings> {
  return parseResponse(await fetch('/api/cloud/settings', { signal, cache: 'no-store' }));
}

export async function putCloudKey(key: string): Promise<void> {
  await parseResponse(await fetch('/api/cloud/key', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Meiyuren-Client': '1' }, body: JSON.stringify({ key }),
  }));
}

export async function deleteCloudKey(): Promise<void> {
  await parseResponse(await fetch('/api/cloud/key', { method: 'DELETE', headers: { 'X-Meiyuren-Client': '1' } }));
}

export async function getCloudModels(): Promise<string[]> {
  const response = await fetch('/api/cloud/models', { cache: 'no-store' });
  return (await parseResponse<{ models: string[] }>(response)).models;
}

export async function putCloudSettings(model: string, enabled: boolean): Promise<void> {
  await parseResponse(await fetch('/api/cloud/settings', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Meiyuren-Client': '1' }, body: JSON.stringify({ model, enabled }),
  }));
}

export type CloudDiagnostics = {
  hasKey: boolean; enabled: boolean; reachable: boolean;
  modelAvailable: boolean; modelsCount: number;
  latencyMs?: number; selectedModel: string; message: string;
};

export async function getCloudDiagnostics(): Promise<CloudDiagnostics> {
  return parseResponse(await fetch('/api/cloud/diagnostics', { cache: 'no-store' }));
}

export type ModelCompatibility = {
  model: string;
  status: 'compatible' | 'incompatible' | 'unknown';
  issues: string[];
  warnings: string[];
  maxModelLen: number | null;
  checkedWithoutGeneration: boolean;
};

export async function getCloudCompatibility(model: string, signal?: AbortSignal): Promise<ModelCompatibility> {
  const url = '/api/cloud/compatibility?model=' + encodeURIComponent(model);
  return parseResponse(await fetch(url, { cache: 'no-store', signal }));
}
