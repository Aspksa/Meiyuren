import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { createServer } from 'vite';
import { findFreePort } from './ports.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const host = '127.0.0.1';

async function start() {
  process.chdir(root);
  const checkedPort = await findFreePort(5173, 100, host);
  if (checkedPort !== 5173) {
    console.log(`\n[Meiyuren] Порт 5173 занят. Найден свободный порт: ${checkedPort}.`);
  } else {
    console.log('\n[Meiyuren] Порт 5173 свободен.');
  }

  // Повторная проверка выполняется самим Vite во время прослушивания:
  // если порт успели занять между проверкой и стартом, Vite выберет следующий.
  const server = await createServer({
    root,
    configFile: resolve(root, 'vite.config.ts'),
    server: { host, port: checkedPort, strictPort: false, open: false },
  });
  await server.listen();
  server.printUrls();

  const address = server.httpServer?.address();
  if (!address || typeof address === 'string') {
    throw new Error('Не удалось определить фактический порт сервера');
  }
  const url = `http://127.0.0.1:${address.port}/`;
  console.log(`[Meiyuren] Готово: ${url}`);
  console.log('[Meiyuren] Чтобы остановить сервер, нажмите Ctrl+C или закройте окно.');

  const command = process.platform === 'win32'
    ? ['cmd.exe', ['/d', '/s', '/c', `start "" "${url}"`]]
    : process.platform === 'darwin'
      ? ['open', [url]]
      : ['xdg-open', [url]];
  try {
    const child = spawn(command[0], command[1], {
      cwd: root,
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    });
    // Отсутствие браузера не должно завершать запущенный веб-сервер.
    child.on('error', () => console.log('[Meiyuren] Откройте адрес из строки «Готово» вручную.'));
    child.unref();
  } catch {
    console.log('[Meiyuren] Откройте адрес из строки «Готово» вручную.');
  }
}

start().catch((error) => {
  console.error('[Meiyuren] Ошибка запуска:', error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
