import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdir, readFile, rename, rm, writeFile, realpath } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import { REPOSITORY_GIT, ciForRevision, needsUpdate, trustedOrigin, validSha } from './updater-policy.mjs';
import { NEEDS_INSTALL, hasZipBackup, installArchive, installedRecord, restoreArchive } from './updater-archive.mjs';

const execFileAsync = promisify(execFile);
const BACKUP_PATH = '.meiyuren/last-update.json';
const GITHUB_API = 'https://api.github.com/repos/Aspksa/Meiyuren';
const ARCHIVE_LIMIT = 100 * 1024 * 1024;
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

async function localVersion(root) {
  try { return JSON.parse(await readFile(join(root, 'package.json'), 'utf8')).version ?? null; } catch { return null; }
}

async function remoteVersion(sha) {
  try {
    const file = await github(`contents/package.json?ref=${sha}`);
    return JSON.parse(Buffer.from(file.content, 'base64').toString('utf8')).version ?? null;
  } catch { return null; }
}

async function remoteState() {
  const [remote, workflows] = await Promise.all([
    github('branches/main'),
    github('actions/runs?branch=main&per_page=30'),
  ]);
  const remoteSha = remote?.commit?.sha;
  if (!validSha(remoteSha)) throw new Error('GitHub вернул некорректную версию.');
  return { remoteSha, ci: ciForRevision(workflows.workflow_runs, remoteSha), remoteVersion: await remoteVersion(remoteSha) };
}

// Сбой сети не должен прятать установленную версию: показываем её вместе с причиной.
async function remoteOrError() {
  try { return { ...(await remoteState()), error: null }; } catch (error) {
    return { remoteSha: null, ci: 'unknown', remoteVersion: null, error: error instanceof Error ? error.message : 'GitHub недоступен.' };
  }
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

// Копия из ZIP-архива: Git нет, версия известна по package.json и записи прошлой установки.
async function checkArchiveUpdates(root) {
  const [{ error, ...remote }, record, installedVersion, canRollback] = await Promise.all([
    remoteOrError(), installedRecord(root), localVersion(root), hasZipBackup(root),
  ]);
  const installedSha = validSha(record?.sha) ? record.sha : null;
  if (error) return { mode: 'archive', installedSha, installedVersion, ...remote, hasUpdate: false, canApply: false, canRollback, message: error };
  const hasUpdate = installedSha !== remote.remoteSha;
  const canApply = hasUpdate && remote.ci === 'success';
  let message = hasUpdate ? 'Доступна новая версия.' : 'Установлена актуальная версия.';
  if (hasUpdate && !installedSha) message = 'Копия из ZIP-архива: точная версия неизвестна. Можно установить последнюю проверенную версию с GitHub.';
  if (hasUpdate && remote.ci === 'pending') message = 'На GitHub ещё выполняются проверки. Обновление пока недоступно.';
  else if (hasUpdate && remote.ci !== 'success') message = 'Нет успешной проверки CI для этой версии. Установка запрещена.';
  return { mode: 'archive', installedSha, installedVersion, ...remote, hasUpdate, canApply, canRollback, message };
}

export async function checkUpdates(root) {
  let local;
  try {
    local = await localState(root);
  } catch {
    if (existsSync(join(root, '.git'))) {
      return {
        mode: 'git', installedSha: null, installedVersion: await localVersion(root), remoteSha: null, remoteVersion: null,
        hasUpdate: false, canApply: false, ci: 'unknown', canRollback: false,
        message: 'Git-копия найдена, но Git недоступен. Установите Git или скачайте свежий ZIP-архив.',
      };
    }
    return checkArchiveUpdates(root);
  }
  const [{ error, ...remote }, record, installedVersion] = await Promise.all([remoteOrError(), readRecord(root), localVersion(root)]);
  const { remoteSha, ci } = remote;
  const hasUpdate = Boolean(remoteSha) && local.sha !== remoteSha;
  const canApply = needsUpdate(local.sha, remoteSha, ci, local.clean, local.trusted, local.branch);
  const canRollback = Boolean(record && record.installedSha === local.sha && local.clean && local.trusted && local.branch === 'main');
  let message = hasUpdate ? 'Новая версия обнаружена.' : 'Установлена актуальная версия.';
  if (!local.trusted) message = 'Источник Git не совпадает с Aspksa/Meiyuren. Обновление запрещено.';
  else if (local.branch !== 'main') message = 'Переключитесь на ветку main.';
  else if (!local.clean) message = 'Есть локальные изменения. Сохраните или отмените их в Git перед обновлением.';
  else if (error) message = error;
  else if (hasUpdate && ci === 'pending') message = 'На GitHub ещё выполняются проверки. Обновление пока недоступно.';
  else if (hasUpdate && ci !== 'success') message = 'Нет успешной проверки CI для этой версии. Установка запрещена.';
  return { mode: 'git', installedSha: local.sha, installedVersion, ...remote, hasUpdate, canApply, canRollback, message };
}

async function downloadArchive(sha) {
  const res = await fetch(`${GITHUB_API}/tarball/${sha}`, {
    headers: { 'User-Agent': 'Meiyuren-Updater', 'Accept': 'application/vnd.github+json' },
    signal: AbortSignal.timeout(120000),
  });
  if (!res.ok) throw new Error(`Не удалось скачать архив версии: HTTP ${res.status}`);
  if (Number(res.headers.get('content-length') ?? 0) > ARCHIVE_LIMIT) throw new Error('Архив обновления слишком большой.');
  const packed = Buffer.from(await res.arrayBuffer());
  if (packed.length > ARCHIVE_LIMIT) throw new Error('Архив обновления слишком большой.');
  return gunzipSync(packed, { maxOutputLength: ARCHIVE_LIMIT * 3 });
}

async function applyArchiveUpdate(root, status) {
  const archive = await downloadArchive(status.remoteSha);
  const result = await installArchive(root, archive, { sha: status.remoteSha, version: status.remoteVersion });
  return {
    success: true,
    message: result.dependenciesChanged
      ? 'Файлы обновлены. Закройте окно Meiyuren и запустите Meiyuren.cmd снова: зависимости установятся автоматически.'
      : 'Файлы обновлены. Закройте окно Meiyuren и запустите Meiyuren.cmd снова.',
    installedSha: status.remoteSha,
  };
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
    if (status.mode === 'archive') return await applyArchiveUpdate(root, status);
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
    // Сохраняем точку отката ДО замены файлов: при сбое записи обновление не начнётся.
    await storeRecord(root, local.sha, fetchedSha);
    try {
      await git(root, 'merge', '--ff-only', fetchedSha);
    } catch (error) {
      // Если Git не обновил HEAD, удаляем неактуальную запись.
      const current = await git(root, 'rev-parse', 'HEAD').catch(() => '');
      if (current === local.sha) await rm(recordFile(root), { force: true });
      throw error;
    }
    const dependencies = await git(root, 'diff', '--name-only', local.sha, fetchedSha, '--', 'package.json', 'package-lock.json').catch(() => '');
    if (dependencies) await writeFile(join(root, NEEDS_INSTALL), 'npm install\n');
    return {
      success: true,
      message: 'Файлы обновлены после успешных проверок GitHub CI. Закройте окно Meiyuren и запустите Meiyuren.cmd снова.',
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
    if (!existsSync(join(root, '.git'))) {
      await restoreArchive(root);
      return {
        success: true,
        message: 'Предыдущая версия файлов восстановлена. Закройте окно Meiyuren и запустите Meiyuren.cmd снова.',
        installedSha: '',
      };
    }
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
