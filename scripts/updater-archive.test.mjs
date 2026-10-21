import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { hasZipBackup, installArchive, installedRecord, parseTar, projectPath, restoreArchive } from './updater-archive.mjs';

function header(name, size, type) {
  const block = Buffer.alloc(512);
  block.write(name, 0, 100, 'utf8');
  block.write('0000644\0', 100, 'ascii');
  block.write(size.toString(8).padStart(11, '0') + '\0', 124, 'ascii');
  block.write(type, 156, 'ascii');
  block.write('ustar\0', 257, 'ascii');
  return block;
}

function entry(name, content, type = '0') {
  const data = Buffer.from(content);
  const padding = Buffer.alloc((512 - (data.length % 512)) % 512);
  return [header(name, data.length, type), data, padding];
}

function tar(files) {
  const parts = [];
  for (const [name, content] of Object.entries(files)) {
    if (Buffer.byteLength(name) > 99) {
      const record = `path=${name}\n`;
      let length = record.length + 3;
      length = `${length} ${record}`.length;
      parts.push(...entry('pax', `${length} ${record}`, 'x'));
      parts.push(...entry('short-name', content));
    } else {
      parts.push(...entry(name, content));
    }
  }
  parts.push(Buffer.alloc(1024));
  return Buffer.concat(parts);
}

const manifest = (version) => JSON.stringify({ name: 'meiyuren', version });

test('Разбор tar понимает длинные имена из pax-заголовков', () => {
  const long = `Aspksa-Meiyuren-abc/${'x'.repeat(120)}.txt`;
  const files = parseTar(tar({ 'Aspksa-Meiyuren-abc/a.txt': 'A', [long]: 'B' }));
  assert.deepEqual(files.map((file) => [file.path, file.data.toString()]), [['Aspksa-Meiyuren-abc/a.txt', 'A'], [long, 'B']]);
});

test('Архив не может писать вне проекта и в пользовательские данные', () => {
  assert.equal(projectPath('top/src/App.tsx'), 'src/App.tsx');
  assert.equal(projectPath('top/data/database.sqlite3'), null);
  assert.equal(projectPath('top/node_modules/x.js'), null);
  assert.equal(projectPath('top/.meiyuren/installed.json'), null);
  assert.throws(() => projectPath('top/../evil.txt'));
  assert.throws(() => projectPath('top/C:/evil.txt'));
});

test('Установка из архива обновляет файлы, сохраняет данные и умеет откатываться', async () => {
  const root = await mkdtemp(join(tmpdir(), 'meiyuren-zip-'));
  try {
    await writeFile(join(root, 'package.json'), manifest('0.1.0'));
    await writeFile(join(root, 'old.txt'), 'старое');
    await mkdir(join(root, 'data'));
    await writeFile(join(root, 'data', 'database.sqlite3'), 'история');

    const archive = tar({
      'Aspksa-Meiyuren-abc/package.json': manifest('0.2.0'),
      'Aspksa-Meiyuren-abc/old.txt': 'новое',
      'Aspksa-Meiyuren-abc/src/new.txt': 'добавлено',
      'Aspksa-Meiyuren-abc/data/database.sqlite3': 'чужое',
    });
    const result = await installArchive(root, archive, { sha: 'a'.repeat(40), version: '0.2.0' });
    assert.equal(result.changed, 3);
    assert.equal(result.dependenciesChanged, true);
    assert.equal(await readFile(join(root, 'old.txt'), 'utf8'), 'новое');
    assert.equal(await readFile(join(root, 'src', 'new.txt'), 'utf8'), 'добавлено');
    assert.equal(await readFile(join(root, 'data', 'database.sqlite3'), 'utf8'), 'история');
    assert.equal((await installedRecord(root)).sha, 'a'.repeat(40));
    assert.equal(existsSync(join(root, '.meiyuren', 'needs-install')), true);
    assert.equal(await hasZipBackup(root), true);

    await restoreArchive(root);
    assert.equal(await readFile(join(root, 'old.txt'), 'utf8'), 'старое');
    assert.equal(JSON.parse(await readFile(join(root, 'package.json'), 'utf8')).version, '0.1.0');
    assert.equal(existsSync(join(root, 'src', 'new.txt')), false);
    assert.equal(await installedRecord(root), null);
    assert.equal(await hasZipBackup(root), false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('Чужой архив не устанавливается', async () => {
  const root = await mkdtemp(join(tmpdir(), 'meiyuren-zip-'));
  try {
    await writeFile(join(root, 'readme.txt'), 'мой файл');
    const archive = tar({ 'evil/package.json': JSON.stringify({ name: 'other' }), 'evil/readme.txt': 'подмена' });
    await assert.rejects(installArchive(root, archive, { sha: 'b'.repeat(40) }));
    assert.equal(await readFile(join(root, 'readme.txt'), 'utf8'), 'мой файл');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
