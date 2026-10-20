import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { updaterPlugin } from './scripts/vite-updates.mjs';

const apiPort = Number(process.env.MEIYUREN_API_PORT ?? '8000');
const backend = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  plugins: [react(), updaterPlugin()],
  server: {
    // Только локальный Python API; модуль обновлений Vite обрабатывает сам.
    proxy: {
      '/api/chat': { target: backend, changeOrigin: false },
      '/api/memory': { target: backend, changeOrigin: false },
      '/api/health': { target: backend, changeOrigin: false },
    },
  },
});
