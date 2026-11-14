import { defineConfig } from '@playwright/test';

/**
 * SPankkiBot UI e2e — runs against the Expo web build at a phone viewport (390x844).
 *
 *   npx playwright test                      # reuses :8081 if running, else starts `expo start --web`
 *   E2E_MOCK=1 npx playwright test           # app uses local fixtures (EXPO_PUBLIC_MOCK=1), no backend needed
 *   E2E_BASE_URL=https://… npx playwright test   # any deployed web build (no local server started)
 *   E2E_NO_SERVER=1                          # never start a server, just connect
 */
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8081';
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';
const startServer = !process.env.E2E_NO_SERVER && !process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  fullyParallel: false, // one Expo dev server; keep the story order stable for screenshots
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000, // LLM answers can take a while
  expect: { timeout: 20_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: BASE_URL,
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: 'en-US',
    timezoneId: 'Europe/Helsinki',
    colorScheme: 'dark',
    navigationTimeout: 120_000, // first Metro web bundle is slow
    actionTimeout: 20_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'mobile-chromium', use: { browserName: 'chromium' } }],
  webServer: startServer
    ? {
        command: 'npx expo start --web --port 8081',
        cwd: '../mobile',
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 240_000,
        stdout: 'ignore',
        stderr: 'pipe',
        env: {
          CI: '1', // non-interactive Expo
          BROWSER: 'none',
          EXPO_PUBLIC_API_URL: API_URL,
          ...(process.env.E2E_MOCK ? { EXPO_PUBLIC_MOCK: '1' } : {}),
        },
      }
    : undefined,
});
