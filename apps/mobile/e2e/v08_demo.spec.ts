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
  await expect(page.getByTestId("public-demo-notice")).toHaveCount(0);
  await expect(page.getByText("Public research demo")).toHaveCount(0);
  await expect(page.getByTestId("account-privacy-panel")).toBeVisible();
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
  await expect(page.getByTestId("public-demo-notice")).toHaveCount(0);
  await expect(page.getByTestId("account-privacy-panel")).toBeVisible();
  await page.getByRole("button", { name: "Manage" }).click();
  await expect(page.getByText(/Signing in is never required/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Turn on Private mode" })).toBeVisible();

  await page.getByRole("button", { name: "Turn on Private mode" }).click();
  await expect(page.getByText(/Private mode is on/).first()).toBeVisible();
  await expect(page.getByText(/temporary server memory only/)).toBeVisible();

  const importRequestPromise = page.waitForRequest((request) => {
    const pathname = new URL(request.url()).pathname;
    return request.method() === "POST" && pathname.endsWith("/records/import");
  });
  await page.getByRole("button", { name: "Load demo" }).click();
  const importRequest = await importRequestPromise;
  const importPayload = importRequest.postDataJSON() as {
    content?: { profile?: { user_id?: unknown } };
  };
  const privateUserId = importPayload.content?.profile?.user_id;
  expect(typeof privateUserId).toBe("string");
  expect(await importRequest.headerValue("x-carepath-private-session")).toBeTruthy();
  const importPathname = new URL(importRequest.url()).pathname;
  const apiPrefix = importPathname.slice(0, -"/records/import".length);

  await expect(page.getByText("Demo loaded")).toBeVisible({ timeout: 30_000 });
  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
  await captureEvidence(page, "private-mode-health-data");

  await page.getByRole("button", { name: "Exit Private mode" }).click();
  await expect(page.getByText(/Private mode is off/)).toBeVisible();
  const persistentProfileStatus = await page.evaluate(
    async ({ prefix, userId }) => {
      const response = await fetch(`${prefix}/profiles/${encodeURIComponent(userId)}`);
      return response.status;
    },
    { prefix: apiPrefix, userId: privateUserId as string },
  );
  expect(persistentProfileStatus).toBe(404);
});

test("language selection translates the complete web interface", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Today dashboard")).toBeVisible();
  await expect(page.getByText("Account & privacy")).toBeVisible();

  await page.getByRole("radio", { name: "Use zh interface safety text" }).click();
  await expect(page.getByText("今日仪表板")).toBeVisible();
  await expect(page.getByText("API 连接")).toBeVisible();
  await expect(page.getByText("账户与隐私")).toBeVisible();
  await expect(page.getByText("Today dashboard")).toHaveCount(0);
  await page.getByRole("button", { name: "加载演示数据" }).click();
  await expect(page.getByText("演示数据已加载")).toBeVisible({ timeout: 30_000 });

  await openTab(page, "tab-health-data");
  await expect(page.getByText("纵向记录")).toBeVisible();
  await expect(page.getByText("原始纵向图表")).toBeVisible();
  await expect(page.getByText("CSV / JSON 导入")).toBeVisible();

  await openTab(page, "tab-coach");
  await expect(page.getByText("基于证据的健康教练")).toBeVisible();
  await expect(page.getByText("询问 CarePath")).toBeVisible();
  await page.getByRole("button", { name: "分析并回答" }).click();
  await expect(page.getByText(/睡眠时长.*近期平均值/).first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(/计划睡觉前.*分钟/).first()).toBeVisible();
  await expect(page.getByText(/sleep_duration decreased/)).toHaveCount(0);
  await expect(page.getByText(/Use 12 minutes for a consistent wind-down cue/)).toHaveCount(0);
  await expect(page.getByText("Internal server error")).toHaveCount(0);

  await openTab(page, "tab-plan-history");
  await expect(page.getByText("长期自适应")).toBeVisible();
  await expect(page.getByText(/查看当前一周计划/)).toBeVisible();

  await page.getByRole("radio", { name: "Use ja interface safety text" }).click();
  await expect(page.getByText("長期的な適応")).toBeVisible();
  await expect(page.getByText(/現在の1週間を確認/)).toBeVisible();
  await expect(page.getByText("アカウントとプライバシー")).toBeVisible();

  await openTab(page, "tab-today");
  await expect(page.getByText("今日のダッシュボード")).toBeVisible();
  await expect(page.getByText("API 接続")).toBeVisible();
  await expect(page.getByText("Today dashboard")).toHaveCount(0);
});

test.describe("mobile browser acceptance", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    screen: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 3,
  });

  test("mobile browser supports the primary journey, tab routing and refresh", async ({ page }) => {
    await page.goto("/");
    expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
    expect(await page.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0);
    await expect(page.getByText("API connection")).toBeVisible();
    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 30_000 });

    await page.getByRole("button", { name: "Load demo" }).click();
    await expect(page.getByText("Demo loaded")).toBeVisible({ timeout: 30_000 });
    await captureEvidence(page, "mobile-today");

    await openTab(page, "tab-health-data");
    await expect(page.getByText("Raw longitudinal chart")).toBeVisible();

    await openTab(page, "tab-coach");
    await expect(page.getByText("Ask CarePath")).toBeVisible();
    await page.getByRole("button", { name: "Analyse and answer" }).click();
    await expect(page.getByText("What I noticed")).toBeVisible({ timeout: 45_000 });

    await openTab(page, "tab-plan-history");
    await expect(page.getByText("Current seven-day plan")).toBeVisible({ timeout: 30_000 });
    await captureEvidence(page, "mobile-primary-journey");

    await page.reload();
    expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
    expect(await page.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0);
    await expect(page.getByText("API connection")).toBeVisible();
    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 30_000 });

    await openTab(page, "tab-health-data");
    await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
    await openTab(page, "tab-today");
    await expect(page.getByText("Today dashboard")).toBeVisible();
    await captureEvidence(page, "mobile-after-refresh");
  });
});

test("desktop reviewer supports refresh and tab routing", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("public-demo-notice")).toHaveCount(0);
  await expect(page.getByText("API connection")).toBeVisible();
  await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 30_000 });

  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
  await openTab(page, "tab-coach");
  await expect(page.getByText("Ask CarePath")).toBeVisible();
  await openTab(page, "tab-plan-history");
  await expect(page.getByRole("heading", { name: "Plan & History" })).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("public-demo-notice")).toHaveCount(0);
  await expect(page.getByText("API connection")).toBeVisible();
  await openTab(page, "tab-health-data");
  await expect(page.getByText("Raw longitudinal chart")).toBeVisible();
});
