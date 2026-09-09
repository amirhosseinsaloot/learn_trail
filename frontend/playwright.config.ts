import { defineConfig, devices } from '@playwright/test';

// Until NU-022 the end-to-end suite runs against the Vite dev server with no
// backend; NU-022 points it at the Compose test stack with the fake model.
// The port comes from the worktree environment (IMPLEMENTATION.md section 4.3).
const vitePort = process.env.NUROLI_DEV_VITE_PORT ?? '5173';
const baseURL = `http://localhost:${vitePort}`;

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: process.env.CI !== undefined,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm exec vite --strictPort',
    url: `${baseURL}/`,
    reuseExistingServer: process.env.CI === undefined,
    timeout: 60_000,
  },
  projects: [
    {
      name: 'desktop-1440',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mobile-390',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
