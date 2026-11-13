import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:8766',
    channel: 'chrome',
    viewport: { width: 1366, height: 768 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'py -3.11 -m uvicorn speaking_evidence.product_api:app --host 127.0.0.1 --port 8766 --no-access-log --log-level warning',
    cwd: '..',
    url: 'http://127.0.0.1:8766/api/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
