import { createServer } from 'node:net';

export async function isPortFree(port, host = '127.0.0.1') {
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new RangeError('Некорректный номер порта');
  }
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', (error) => {
      if (error.code === 'EADDRINUSE' || error.code === 'EACCES') {
        resolve(false);
      } else {
        reject(error);
      }
    });
    probe.listen({ host, port, exclusive: true }, () => {
      probe.close((error) => error ? reject(error) : resolve(true));
    });
  });
}

export async function findFreePort(start = 5173, attempts = 100, host = '127.0.0.1') {
  if (!Number.isInteger(start) || !Number.isInteger(attempts) || start < 1 || attempts < 1 || start + attempts - 1 > 65535) {
    throw new RangeError('Некорректный диапазон портов');
  }
  for (let port = start; port < start + attempts; port += 1) {
    if (await isPortFree(port, host)) return port;
  }
  throw new Error(`Нет свободного порта в диапазоне ${start}–${start + attempts - 1}`);
}
