import { expect, test, type Page } from "@playwright/test";
import { mkdir, stat } from "node:fs/promises";

const screenshots = "../../docs/evidence/v08/screenshots";

async function openTab(page: Page, nativeId: string): Promise<void> {
  const tab = page.locator(`#${nativeId}`).first();
  await expect(tab).toBeVisible();
  await tab.click();
}

async function captureEvidence(page: Page, name: string): Promise<void> {
  const path = `${screenshots}/${name}.png`;
  await page.screenshot({ animations: "disabled", path });
  await expect.poll(async () => (await stat(path)).size).toBeGreaterThan(5_000);
}

test.beforeAll(async () => {
  await mkdir(screenshots, { recursive: true });
});

test("real backend primary journey records a two-round feedback-adaptation flow", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("public-demo-notice")).toBeVisible();
  await expect(page.getByText(/Submitted data may be retained on the demo server/)).toBeVisible();
  await expect(page.getByText("API connection")).toBeVisible();
  await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: "Jordan Lee" }).click();
  await expect(
    page.getByText("Remote worker with stable sleep but a recent drop in daily movement."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load demo" }).click();
  await expect(page.getByText("Demo loaded")).toBeVisible({ timeout: 30_000 });
  await captureEvidence(page, "today");

  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
  await captureEvidence(page, "health-data");

  await openTab(page, "tab-coach");
  await page.getByRole("button", { name: "Analyse and answer" }).click();
  await expect(page.getByText("What I noticed")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/Take a 12-minute comfortable walk/).first()).toBeVisible();
  const exactChunk = page.getByText("Show exact chunk");
  if ((await exactChunk.count()) > 0) {
    await exactChunk.first().click();
  }
  await captureEvidence(page, "coach");

  await openTab(page, "tab-plan-history");
  await expect(page.getByText("Current seven-day plan")).toBeVisible({ timeout: 30_000 });
  const reason = page.getByPlaceholder("Reason, constraint or what made this difficult").first();
  await reason.fill("The original action is too difficult this week.");
  await page.getByRole("button", { name: "Choose lighter option" }).first().click();
  await expect(page.getByText("Feedback saved")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("modified").first()).toBeVisible();
  await captureEvidence(page, "plan-history");

  await openTab(page, "tab-coach");
  await page.getByRole("button", { name: "Analyse and answer" }).click();
  await expect(page.getByText("What I noticed")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/Take an 8-minute comfortable walk/).first()).toBeVisible();
  await expect(page.getByText(/Take a 12-minute comfortable walk/)).toHaveCount(0);
  await captureEvidence(page, "coach-after-feedback");

  await openTab(page, "tab-plan-history");
  await expect(page.getByText("Current seven-day plan")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("modified").first()).toBeVisible();
  await captureEvidence(page, "plan-history-return");
});

test("Private mode uses an isolated non-persistent workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("account-privacy-panel")).toBeVisible();
  await page.getByRole("button", { name: "Manage" }).click();
  await expect(page.getByText(/Signing in is never required/)).toBeVisible();
  await expect(page.getByText(/Account sign-in is not configured/)).toBeVisible();

  await page.getByRole("button", { name: "Turn on Private mode" }).click();
  await expect(page.getByText("Public research demo · Private mode")).toBeVisible();
  await expect(page.getByText(/not written to the persistent CarePath database/)).toBeVisible();
  await expect(page.getByText(/temporary server memory only/)).toBeVisible();

  await page.getByRole("button", { name: "Load demo" }).click();
  await expect(page.getByText("Demo loaded")).toBeVisible({ timeout: 30_000 });
  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
  await captureEvidence(page, "private-mode-health-data");

  await page.getByRole("button", { name: "Exit Private mode" }).click();
  await expect(page.getByText("Public research demo")).toBeVisible();
  await expect(page.getByText(/Submitted data may be retained on the demo server/)).toBeVisible();
  await expect(page.getByText("Demo loaded")).toHaveCount(0);
});

test("desktop reviewer supports refresh and tab routing", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("public-demo-notice")).toBeVisible();
  await expect(page.getByText("API connection")).toBeVisible();
  await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 30_000 });

  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
  await openTab(page, "tab-coach");
  await expect(page.getByText("Ask CarePath")).toBeVisible();
  await openTab(page, "tab-plan-history");
  await expect(page.getByRole("heading", { name: "Plan & History" })).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("public-demo-notice")).toBeVisible();
  await expect(page.getByText("API connection")).toBeVisible();
  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
});
