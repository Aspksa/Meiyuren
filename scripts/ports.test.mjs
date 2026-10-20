import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { test } from 'node:test';
import { findFreePort, isPortFree } from './ports.mjs';

test('некорректный порт отклоняется', async () => {
  await assert.rejects(isPortFree(0), RangeError);
  await assert.rejects(findFreePort(65535, 2), RangeError);
});

test('занятый порт пропускается', async () => {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    assert.equal(await isPortFree(address.port), false);
    const free = await findFreePort(address.port, 2);
    assert.equal(free, address.port + 1);
    assert.equal(await isPortFree(free), true);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
