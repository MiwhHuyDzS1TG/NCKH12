import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.ts',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    channel: 'chrome',
    viewport: { width: 1920, height: 1080 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'corepack pnpm dev --host 127.0.0.1 --port 4173',
    port: 4173,
    reuseExistingServer: true,
  },
});
