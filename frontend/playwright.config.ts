import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke tests: a fake-AI backend (no key, no cost, fresh database)
 * and a production build of the dashboard, on their own ports.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // Answers stream over a few seconds, and the first test meets a cold browser and servers.
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3100",
    trace: "retain-on-failure",
    // A fake microphone (a test tone) for the voice tests.
    permissions: ["microphone"],
    launchOptions: {
      args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
    },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
      timeout: 180_000, // allow cold Windows imports/migrations while the backend suite is also running
    },
    {
      command: "npx next build && npx next start -p 3100",
      url: "http://localhost:3100",
      reuseExistingServer: false,
      timeout: 240_000,
      env: { NEXT_DIST_DIR: ".next-e2e", NEXT_PUBLIC_BACKEND_URL: "http://127.0.0.1:8100" },
    },
  ],
});
