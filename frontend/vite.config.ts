import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Ports come from the worktree environment (IMPLEMENTATION.md section 4.3) so
// two worktrees can run Vite and the API side by side; the main checkout
// uses the defaults.
const apiPort = process.env.NUROLI_DEV_API_PORT ?? '8000';
const vitePort = Number(process.env.NUROLI_DEV_VITE_PORT ?? '5173');

export default defineConfig({
  plugins: [react()],
  server: {
    port: vitePort,
    strictPort: true,
    proxy: {
      '/api': { target: `http://localhost:${apiPort}` },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
