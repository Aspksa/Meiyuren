import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { findFreePort } from './ports.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const host = '127.0.0.1';

function locatePython() {
  const local = process.platform === 'win32'
    ? join(root, 'backend', '.venv', 'Scripts', 'python.exe')
    : join(root, 'backend', '.venv', 'bin', 'python');
  const options = [];
  if (existsSync(local)) options.push([local, []]);
  if (process.platform === 'win32') options.push(['py', ['-3']], ['python', []]);
  else options.push(['python3', []], ['python', []]);
  for (const [command, prefix] of options) {
    const probe = spawnSync(command, [...prefix, '-c', 'import fastapi, uvicorn'], {
      cwd: root, timeout: 5000, windowsHide: true, encoding: 'utf8',
    });
    if (probe.status === 0) return { command, prefix };
  }
  return null;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function startBackend() {
  const python = locatePython();
  if (!python) {
    console.warn('[Meiyuren] Python/FastAPI не готовы. Выполните setup-python.cmd (Windows) или инструкции README.');
    console.warn('[Meiyuren] Сайт откроется, но чат и память будут недоступны.');
    process.env.MEIYUREN_API_PORT = '8000';
    return null;
  }
  const port = await findFreePort(8000, 100, host);
  process.env.MEIYUREN_API_PORT = String(port);
  const args = [...python.prefix, '-m', 'uvicorn', 'backend.app.main:app', '--host', host, '--port', String(port)];
  const child = spawn(python.command, args, { cwd: root, stdio: 'inherit', windowsHide: false });
  child.on('error', (error) => console.warn('[Meiyuren] Ошибка Python-сервера:', error.message));
  child.on('exit', (code) => {
    if (code !== null && code !== 0) console.warn('[Meiyuren] Python-сервер остановился. Код:', code);
  });
  const url = `http://${host}:${port}/api/health`;
  let healthy = false;
  for (let i = 0; i < 48; i += 1) {
    if (child.exitCode !== null) break;
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(450) });
      if (response.ok) { healthy = true; break; }
    } catch { /* Python ещё запускается */ }
    await sleep(250);
  }
  if (healthy) console.log(`[Meiyuren] Python API запущен: http://${host}:${port}`);
  else console.warn('[Meiyuren] Python API не ответил вовремя. Проверьте консоль, затем перезапустите.');
  return child;
}

function openBrowser(url) {
  const command = process.platform === 'win32'
    ? ['cmd.exe', ['/d', '/s', '/c', `start "" "${url}"`]]
    : process.platform === 'darwin'
      ? ['open', [url]]
      : ['xdg-open', [url]];
  try {
    const child = spawn(command[0], command[1], {
      cwd: root, detached: true, stdio: 'ignore', windowsHide: true,
    });
    child.on('error', () => console.log('[Meiyuren] Откройте адрес из консоли вручную.'));
    child.unref();
  } catch {
    console.log('[Meiyuren] Откройте адрес из консоли вручную.');
  }
}

async function start() {
  process.chdir(root);
  const backend = await startBackend();
  if (backend) {
    process.once('exit', () => backend.kill());
    for (const signal of ['SIGINT', 'SIGTERM']) {
      process.once(signal, () => { backend.kill(); process.exit(0); });
    }
  }
  const port = await findFreePort(5173, 100, host);
  const server = await createServer({
    root,
    configFile: resolve(root, 'vite.config.ts'),
    server: { host, port, strictPort: false, open: false },
  });
  await server.listen();
  server.printUrls();
  const address = server.httpServer?.address();
  if (!address || typeof address === 'string') throw new Error('Не удалось определить порт сайта.');
  const url = `http://${host}:${address.port}/`;
  console.log(`[Meiyuren] Сайт: ${url}`);
  console.log('[Meiyuren] Остановить: Ctrl+C.');
  openBrowser(url);
}

start().catch((error) => {
  console.error('[Meiyuren] Ошибка запуска:', error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
