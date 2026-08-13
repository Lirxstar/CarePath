import { defineConfig } from "@playwright/test";

const baseURL = process.env.CAREPATH_E2E_BASE_URL;
if (!baseURL) {
  throw new Error("CAREPATH_E2E_BASE_URL is required for CP-209 screenshot capture");
}

export default defineConfig({
  testDir: ".",
  testMatch: ["**/cp209_submission_capture.spec.ts"],
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    ignoreHTTPSErrors: false,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  outputDir: "test-results/cp209",
});
