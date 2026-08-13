import { defineConfig } from "@playwright/test";

const baseURL = process.env.CAREPATH_E2E_BASE_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: ".",
  testMatch: ["**/tokyo_public.spec.ts"],
  timeout: 90_000,
  expect: {
    timeout: 20_000,
  },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    ignoreHTTPSErrors: false,
    screenshot: "on",
    trace: "retain-on-failure",
  },
  outputDir: "test-results/cp208",
});
