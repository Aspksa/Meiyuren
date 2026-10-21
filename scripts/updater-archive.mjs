// Обновление копии, распакованной из ZIP-архива (без Git): архив версии с GitHub
// раскладывается поверх файлов проекта, а заменённые файлы сохраняются для отката.
import { copyFile, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';

export const STATE_DIR = '.meiyuren';
const BACKUP_DIR = join(STATE_DIR, 'zip-backup');
const BACKUP_RECORD = join(STATE_DIR, 'zip-backup.json');
const INSTALLED_RECORD = join(STATE_DIR, 'installed.json');
export const NEEDS_INSTALL = join(STATE_DIR, 'needs-install');

// Пользовательские данные и окружение никогда не перезаписываются архивом.
const PROTECTED = ['.git', '.meiyuren', 'node_modules', 'data', 'runtime', 'backend/.venv'];

function octal(buffer, start, length) {
  const text = buffer.toString('ascii', start, start + length).replace(/\0.*$/s, '').trim();
  return text ? parseInt(text, 8) : 0;
}

function text(buffer, start, length) {
  return buffer.toString('utf8', start, start + length).replace(/\0.*$/s, '');
}

function paxPath(data) {
  let offset = 0;
  let path = null;
  const raw = data.toString('utf8');
  while (offset < raw.length) {
    const space = raw.indexOf(' ', offset);
    const length = Number(raw.slice(offset, space));
    if (!Number.isInteger(length) || length <= 0) break;
    const record = raw.slice(space + 1, offset + length - 1);
    if (record.startsWith('path=')) path = record.slice(5);
    offset += length;
  }
  return path;
}

/** Разбирает tar (ustar + pax/GNU длинные имена). Возвращает только файлы. */
export function parseTar(buffer) {
  const files = [];
  let offset = 0;
  let longName = null;
  while (offset + 512 <= buffer.length) {
    const header = buffer.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;
    const size = octal(header, 124, 12);
    const type = String.fromCharCode(header[156] || 48);
    const prefix = text(header, 345, 155);
    const name = longName ?? (prefix ? `${prefix}/${text(header, 0, 100)}` : text(header, 0, 100));
    const data = buffer.subarray(offset + 512, offset + 512 + size);
    offset += 512 + Math.ceil(size / 512) * 512;
    if (type === 'x') { longName = paxPath(data); continue; }
    if (type === 'L') { longName = data.toString('utf8').replace(/\0.*$/s, ''); continue; }
    longName = null;
    if (type === '0' || type === '7') files.push({ path: name, mode: octal(header, 100, 8), data: Buffer.from(data) });
  }
  return files;
}

/** Путь внутри проекта без первого каталога архива (Aspksa-Meiyuren-<sha>/). */
export function projectPath(archivePath) {
  const parts = archivePath.replace(/\\/g, '/').split('/').slice(1).filter(Boolean);
  if (parts.length === 0) return null;
  if (parts.some((part) => part === '..' || part === '.' || part.includes(':'))) {
    throw new Error('Архив содержит недопустимый путь.');
  }
  const path = parts.join('/');
  if (PROTECTED.some((item) => path === item || path.startsWith(`${item}/`))) return null;
  return path;
}

async function readJSON(file) {
  try { return JSON.parse(await readFile(file, 'utf8')); } catch { return null; }
}

export async function installedRecord(root) {
  return readJSON(join(root, INSTALLED_RECORD));
}

export async function hasZipBackup(root) {
  const record = await readJSON(join(root, BACKUP_RECORD));
  return Boolean(record && Array.isArray(record.replaced) && Array.isArray(record.created));
}

async function writeAtomic(target, data, mode) {
  await mkdir(dirname(target), { recursive: true });
  const temporary = `${target}.meiyuren-tmp`;
  await writeFile(temporary, data, { mode: mode & 0o111 ? 0o755 : 0o644 });
  await rename(temporary, target);
}

/** Раскладывает файлы архива поверх проекта; прежние версии сохраняются для отката. */
export async function installArchive(root, tarBuffer, installed) {
  const files = parseTar(tarBuffer)
    .map((file) => ({ ...file, path: projectPath(file.path) }))
    .filter((file) => file.path);
  const manifest = files.find((file) => file.path === 'package.json');
  if (!manifest || JSON.parse(manifest.data.toString('utf8')).name !== 'meiyuren') {
    throw new Error('Загруженный архив не похож на Meiyuren. Установка отменена.');
  }

  await rm(join(root, BACKUP_DIR), { recursive: true, force: true });
  const replaced = [];
  const created = [];
  let dependenciesChanged = false;
  // Сначала сохраняем всё, что будет заменено: при сбое копирования файлы проекта не тронуты.
  for (const file of files) {
    const target = join(root, file.path);
    if (!existsSync(target)) { created.push(file.path); continue; }
    const current = await readFile(target);
    if (current.equals(file.data)) continue;
    await mkdir(dirname(join(root, BACKUP_DIR, file.path)), { recursive: true });
    await copyFile(target, join(root, BACKUP_DIR, file.path));
    replaced.push(file.path);
    if (file.path === 'package.json' || file.path === 'package-lock.json') dependenciesChanged = true;
  }
  const previous = await installedRecord(root);
  await writeAtomic(join(root, BACKUP_RECORD), JSON.stringify({ previous, replaced, created }, null, 2), 0o600);

  const changed = new Set([...replaced, ...created]);
  for (const file of files) {
    if (changed.has(file.path)) await writeAtomic(join(root, file.path), file.data, file.mode);
  }
  if (dependenciesChanged) await writeAtomic(join(root, NEEDS_INSTALL), 'npm install\n', 0o644);
  await writeAtomic(join(root, INSTALLED_RECORD), JSON.stringify({ ...installed, installedAt: new Date().toISOString() }, null, 2), 0o644);
  return { changed: changed.size, dependenciesChanged };
}

/** Возвращает файлы, заменённые последним обновлением из архива. */
export async function restoreArchive(root) {
  const record = await readJSON(join(root, BACKUP_RECORD));
  if (!record || !Array.isArray(record.replaced) || !Array.isArray(record.created)) {
    throw new Error('Нет сохранённой предыдущей версии.');
  }
  const safe = (path) => projectPath(`root/${path}`);
  for (const path of record.replaced.map(safe).filter(Boolean)) {
    await writeAtomic(join(root, path), await readFile(join(root, BACKUP_DIR, path)), 0o644);
  }
  for (const path of record.created.map(safe).filter(Boolean)) {
    await rm(join(root, path), { force: true });
  }
  if (record.replaced.includes('package.json') || record.replaced.includes('package-lock.json')) {
    await writeAtomic(join(root, NEEDS_INSTALL), 'npm install\n', 0o644);
  }
  if (record.previous) await writeAtomic(join(root, INSTALLED_RECORD), JSON.stringify(record.previous, null, 2), 0o644);
  else await rm(join(root, INSTALLED_RECORD), { force: true });
  await rm(join(root, BACKUP_DIR), { recursive: true, force: true });
  await rm(join(root, BACKUP_RECORD), { force: true });
}
