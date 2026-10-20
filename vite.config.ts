import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { updaterPlugin } from './scripts/vite-updates.mjs';

export default defineConfig({
  plugins: [react(), updaterPlugin()],
});
