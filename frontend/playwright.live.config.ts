import { defineConfig, devices } from '@playwright/test';

// Smoke checks against an already-deployed frontend (see scripts/smoke-ui.sh); no dev server.
export default defineConfig({
  testDir: './tests/e2e-live',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'http://localhost:18080',
    ignoreHTTPSErrors: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
