import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, readFile, rename, rm, writeFile, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { REPOSITORY_GIT, ciForRevision, needsUpdate, trustedOrigin, validSha } from './updater-policy.mjs';

const execFileAsync = promisify(execFile);
const BACKUP_PATH = '.meiyuren/last-update.json';
const GITHUB_API = 'https://api.github.com/repos/Aspksa/Meiyuren';
const GIT_OPTIONS = { timeout: 90000, maxBuffer: 512 * 1024, windowsHide: true, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } };

async function git(root, ...args) {
  const { stdout } = await execFileAsync('git', ['-C', root, ...args], GIT_OPTIONS);
  return stdout.trim();
}

async function github(path) {
  const res = await fetch(`${GITHUB_API}/${path}`, {
    headers: {
      'Accept': 'application/vnd.github+json',
      'User-Agent': 'Meiyuren-Updater',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(res.status === 403 ? 'GitHub ограничил запросы. Повторите позже.' : `GitHub API: HTTP ${res.status}`);
  return res.json();
}

function recordFile(root) { return join(root, BACKUP_PATH); }
async function readRecord(root) {
  try {
    const record = JSON.parse(await readFile(recordFile(root), 'utf8'));
    return validSha(record.previousSha) && validSha(record.installedSha) ? record : null;
  } catch { return null; }
}

async function localState(root) {
  const base = await realpath(root);
  const top = await realpath(await git(root, 'rev-parse', '--show-toplevel'));
  if (base.toLowerCase() !== top.toLowerCase()) {
    throw new Error('Обновлять можно только корень клонированного проекта.');
  }
  const [sha, branch, origin, changes] = await Promise.all([
    git(root, 'rev-parse', 'HEAD'),
    git(root, 'branch', '--show-current'),
    git(root, 'remote', 'get-url', 'origin'),
    git(root, 'status', '--porcelain', '--untracked-files=normal'),
  ]);
  return { sha, branch, trusted: trustedOrigin(origin), clean: changes.length === 0 };
}

let activeOperation = false;

export async function checkUpdates(root) {
  let local;
  try {
    local = await localState(root);
  } catch {
    return {
      installedSha: null, remoteSha: null, hasUpdate: false, canApply: false,
      ci: 'unknown', canRollback: false,
      message: 'Для обновления из приложения нужна Git-копия проекта (git clone), а не ZIP-архив. Можно проверить GitHub вручную.',
    };
  }
  const [remote, workflows, record] = await Promise.all([
    github('branches/main'),
    github('actions/runs?branch=main&per_page=30'),
    readRecord(root),
  ]);
  const remoteSha = remote?.commit?.sha;
  if (!validSha(remoteSha)) throw new Error('GitHub вернул некорректную версию.');
  const ci = ciForRevision(workflows.workflow_runs, remoteSha);
  const hasUpdate = local.sha !== remoteSha;
  const canApply = needsUpdate(local.sha, remoteSha, ci, local.clean, local.trusted, local.branch);
  const canRollback = Boolean(record && record.installedSha === local.sha && local.clean && local.trusted && local.branch === 'main');
  let message = hasUpdate ? 'Новая версия обнаружена.' : 'Установлена актуальная версия.';
  if (!local.trusted) message = 'Источник Git не совпадает с Aspksa/Meiyuren. Обновление запрещено.';
  else if (local.branch !== 'main') message = 'Переключитесь на ветку main.';
  else if (!local.clean) message = 'Есть локальные изменения. Сохраните или отмените их в Git перед обновлением.';
  else if (hasUpdate && ci === 'pending') message = 'На GitHub ещё выполняются проверки. Обновление пока недоступно.';
  else if (hasUpdate && ci !== 'success') message = 'Нет успешной проверки CI для этой версии. Установка запрещена.';
  return { installedSha: local.sha, remoteSha, hasUpdate, canApply, ci, canRollback, message };
}

async function storeRecord(root, previousSha, installedSha) {
  const dir = join(root, '.meiyuren');
  await mkdir(dir, { recursive: true });
  const destination = recordFile(root);
  const temporary = `${destination}.tmp`;
  await writeFile(temporary, JSON.stringify({ previousSha, installedSha, savedAt: new Date().toISOString() }, null, 2), { mode: 0o600 });
  await rename(temporary, destination);
}

export async function applyUpdate(root, expectedSha) {
  if (activeOperation) throw new Error('Обновление уже выполняется.');
  if (!validSha(expectedSha)) throw new Error('Некорректный идентификатор версии.');
  activeOperation = true;
  try {
    const status = await checkUpdates(root);
    if (!status.canApply || status.remoteSha !== expectedSha) {
      throw new Error('Версия изменилась или проверка не пройдена. Проверьте обновления повторно.');
    }
    await git(root, 'fetch', '--no-tags', REPOSITORY_GIT, 'refs/heads/main');
    const fetchedSha = await git(root, 'rev-parse', 'FETCH_HEAD');
    if (fetchedSha !== expectedSha) throw new Error('Ветка GitHub изменилась во время загрузки. Установка отменена.');
    const local = await localState(root);
    if (!local.clean || local.branch !== 'main' || !local.trusted || local.sha !== status.installedSha) {
      throw new Error('Локальная копия изменилась. Установка отменена.');
    }
    try {
      await git(root, 'merge-base', '--is-ancestor', local.sha, fetchedSha);
    } catch {
      throw new Error('Истории Git разошлись. Автоматическое объединение запрещено.');
    }
    await git(root, 'merge', '--ff-only', fetchedSha);
    await storeRecord(root, local.sha, fetchedSha);
    return {
      success: true,
      message: 'Файлы обновлены после успешных проверок GitHub CI. Перезапустите Meiyuren.cmd; если изменились зависимости, выполните npm install.',
      installedSha: fetchedSha,
    };
  } finally {
    activeOperation = false;
  }
}

export async function rollbackUpdate(root) {
  if (activeOperation) throw new Error('Другая операция уже выполняется.');
  activeOperation = true;
  try {
    const record = await readRecord(root);
    if (!record) throw new Error('Нет сохранённой предыдущей версии.');
    const local = await localState(root);
    if (!local.clean || !local.trusted || local.branch !== 'main' || local.sha !== record.installedSha) {
      throw new Error('Локальные файлы изменены или версия не совпадает. Откат запрещён.');
    }
    try {
      await git(root, 'merge-base', '--is-ancestor', record.previousSha, local.sha);
    } catch {
      throw new Error('Не найдена подтверждённая предыдущая версия.');
    }
    // Рабочая копия проверена как чистая, а HEAD точно совпадает с установленной версией.
    await git(root, 'reset', '--hard', record.previousSha);
    await rm(recordFile(root), { force: true });
    return {
      success: true,
      message: 'Предыдущая версия кода восстановлена. Перезапустите Meiyuren.cmd. Для зависимостей при необходимости выполните npm install.',
      installedSha: record.previousSha,
    };
  } finally {
    activeOperation = false;
  }
}
