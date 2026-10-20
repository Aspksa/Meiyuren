import assert from 'node:assert/strict';
import test from 'node:test';
import { updaterPlugin } from './vite-updates.mjs';

function fakeResponse() {
  return {
    statusCode: 200,
    headers: {},
    setHeader(key, value) { this.headers[key] = value; },
    end(value) { this.body = JSON.parse(value); },
  };
}

function middleware() {
  let handler;
  updaterPlugin().configureServer({
    config: { root: '/tmp' },
    middlewares: { use(next) { handler = next; } },
  });
  return handler;
}

test('Updater API запрещает входящие запросы с нелокального IP', async () => {
  const fn = middleware();
  const res = fakeResponse();
  await fn({ url: '/api/updates/status', method: 'GET', headers: { host: '127.0.0.1:5173' }, socket: { remoteAddress: '192.168.1.10' } }, res, () => {});
  assert.equal(res.statusCode, 403);
});

test('Updater API не принимает запросы через чужой Host', async () => {
  const fn = middleware();
  const res = fakeResponse();
  await fn({ url: '/api/updates/status', method: 'GET', headers: { host: 'external.example:5173' }, socket: { remoteAddress: '127.0.0.1' } }, res, () => {});
  assert.equal(res.statusCode, 403);
});

test('POST требует совпадающий Origin, JSON и специальный заголовок', async () => {
  const fn = middleware();
  for (const headers of [
    { host: '127.0.0.1:5173' },
    { host: '127.0.0.1:5173', origin: 'http://attacker.example', 'content-type': 'application/json', 'x-meiyuren-confirm': 'yes' },
    { host: '127.0.0.1:5173', origin: 'http://127.0.0.1:5173', 'content-type': 'application/json' },
    { host: '127.0.0.1:5173', origin: 'http://127.0.0.1:5173', 'x-meiyuren-confirm': 'yes', 'content-type': 'text/plain' },
  ]) {
    const res = fakeResponse();
    await fn({ url: '/api/updates/apply', method: 'POST', headers, socket: { remoteAddress: '127.0.0.1' } }, res, () => {});
    assert.equal(res.statusCode, 403);
  }
});

test('Неизвестные маршруты передаются Vite', async () => {
  const fn = middleware();
  let nextCalled = false;
  await fn({ url: '/src/App.tsx' }, {}, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
});
