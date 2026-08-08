import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "v08_demo.spec.ts",
  timeout: 90_000,
  retries: 0,
  workers: 1,
  outputDir: "../../../docs/evidence/v08/run",
  use: {
    baseURL: process.env.CAREPATH_E2E_BASE_URL ?? "http://127.0.0.1:4173",
    viewport: { width: 390, height: 844 },
    video: "on",
    trace: "on",
  },
});
