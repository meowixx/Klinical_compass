import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 45000,
  reporter: [['list'], ['html', { outputFolder: 'audit-results/playwright', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:3130', headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: '..\\.venv\\Scripts\\python.exe ..\\scripts\\audit_server.py', url: 'http://127.0.0.1:8011/health', reuseExistingServer: true },
    { command: 'npm run dev -- --port 3130', url: 'http://127.0.0.1:3130', reuseExistingServer: true,
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8011/api/v1', NEXT_PUBLIC_DATA_SOURCE: 'api', NEXT_DIST_DIR: '.audit-next' } },
  ],
});
