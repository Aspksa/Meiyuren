import { resolve } from 'node:path';
import { applyUpdate, checkUpdates, rollbackUpdate } from './updater-service.mjs';

const PREFIX = '/api/updates';

function safeRequest(req) {
  const ip = req.socket.remoteAddress;
  if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(ip)) return false;
  return /^(127\.0\.0\.1|localhost):\d{1,5}$/.test(req.headers.host ?? '');
}

function json(res, code, payload) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(JSON.stringify(payload));
}

async function readJSON(req) {
  let text = '';
  for await (const chunk of req) {
    text += chunk;
    if (text.length > 2048) throw new Error('Слишком большой запрос.');
  }
  return JSON.parse(text || '{}');
}

export function updaterPlugin() {
  return {
    name: 'meiyuren-local-update-api',
    apply: 'serve',
    configureServer(server) {
      const root = resolve(server.config.root);
      server.middlewares.use(async (req, res, next) => {
        const path = req.url?.split('?')[0];
        if (!path?.startsWith(PREFIX)) return next();
        if (!safeRequest(req)) return json(res, 403, { message: 'Доступ только с этого компьютера.' });
        try {
          if (path === `${PREFIX}/status` && req.method === 'GET') {
            return json(res, 200, await checkUpdates(root));
          }
          if (req.method !== 'POST' || ![`${PREFIX}/apply`, `${PREFIX}/rollback`].includes(path)) {
            return json(res, 404, { message: 'Неизвестная команда обновления.' });
          }
          const origin = req.headers.origin;
          if (origin !== `http://${req.headers.host}` ||
              req.headers['x-meiyuren-confirm'] !== 'yes' ||
              !req.headers['content-type']?.startsWith('application/json')) {
            return json(res, 403, { message: 'Действие требует подтверждения из локального приложения.' });
          }
          const body = await readJSON(req);
          if (path === `${PREFIX}/apply`) {
            if (body.confirm !== 'apply') return json(res, 400, { message: 'Обновление не подтверждено.' });
            return json(res, 200, await applyUpdate(root, body.expectedSha));
          }
          if (body.confirm !== 'rollback') return json(res, 400, { message: 'Откат не подтверждён.' });
          return json(res, 200, await rollbackUpdate(root));
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Ошибка';
          return json(res, 409, { message });
        }
      });
    },
  };
}
