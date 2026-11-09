/**
 * End-to-end tests: real browser, real FastAPI backend (mock inference provider), real Next app.
 *
 *   npm run e2e                                # bundled Chromium (`npx playwright install chromium`)
 *   PLAYWRIGHT_CHANNEL=chrome npm run e2e      # use the locally installed Google Chrome instead
 *
 * Locally, already-running dev servers on :8000 / :3000 are reused. In CI both are started here;
 * the backend writes to `backend/var/e2e` (git-ignored) and never touches real user data.
 */

import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;
const python = process.platform === "win32" ? ".venv\\Scripts\\python" : ".venv/bin/python";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: CI ? 1 : 0,
  workers: 1, // tests share one backend database
  reporter: CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://localhost:3000",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/v1/health",
      env: {
        SKETCHLOGIC_DATA_DIR: "var/e2e",
        SKETCHLOGIC_INFERENCE_PROVIDER: "mock",
        SKETCHLOGIC_AWS_ENABLED: "false",
      },
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      // CI runs `npm run build` first; locally reuse (or start) the dev server.
      command: CI ? "npm run start" : "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !CI,
      timeout: 180_000,
    },
  ],
});
