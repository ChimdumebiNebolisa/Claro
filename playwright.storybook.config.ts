import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/storybook",
  timeout: 180_000,
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:6006",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "node scripts/serve-static.mjs storybook-static 6006",
    url: "http://127.0.0.1:6006/index.json",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
