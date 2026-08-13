import { expect, test, type Page } from "@playwright/test";

async function chooseManualLocation(page: Page, municipality: string) {
  await page.getByTestId("tokyo-manual-location").fill(municipality);
  await page.getByTestId("tokyo-use-manual-location").click();
  await expect(page.getByTestId("tokyo-selected-location")).toContainText(municipality);
}

async function search(page: Page, query: string, municipality: string) {
  await page.getByTestId("tokyo-query").fill(query);
  await chooseManualLocation(page, municipality);
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-testid^="tokyo-resource-"]').first()).toBeVisible();
  await expect(page.locator('[data-testid^="tokyo-source-"]').first()).toBeVisible();
}

async function captureExternalOpen(page: Page, testIdPrefix: string) {
  const button = page.locator(`[data-testid^="${testIdPrefix}"]`).first();
  if ((await button.count()) === 0) {
    return null;
  }
  await page.evaluate(() => {
    window.sessionStorage.removeItem("carepath-cp208-open-url");
    window.open = ((url?: string | URL) => {
      window.sessionStorage.setItem("carepath-cp208-open-url", String(url ?? ""));
      return null;
    }) as typeof window.open;
  });
  await button.click();
  return page.evaluate(() => window.sessionStorage.getItem("carepath-cp208-open-url"));
}

test("public Tokyo route survives hard refresh and completes EN JA ZH source-backed journeys", async ({
  page,
}) => {
  await page.goto("/tokyo");
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("account-privacy-panel")).toHaveCount(0);
  await expect(page).toHaveURL(/\/tokyo\/?$/);

  await page.reload();
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({ timeout: 60_000 });
  await expect(page).toHaveURL(/\/tokyo\/?$/);

  await page.getByTestId("tokyo-language-en").click();
  await search(
    page,
    "I need a nearby clinic in Tokyo where staff can support me in English.",
    "新宿区",
  );
  await expect(page.getByText("Verified source facts").first()).toBeVisible();

  await page.getByTestId("tokyo-language-ja").click();
  await search(page, "とても暑いので、近くの指定クーリングシェルターを探したいです。", "江東区");
  await expect(page.getByText("確認済みの出典情報").first()).toBeVisible();

  await page.getByTestId("tokyo-language-zh").click();
  await search(
    page,
    "我在育儿方面遇到困难，但不知道应该联系东京的哪种公共支持服务。",
    "江東区",
  );
  await expect(page.getByText("经来源验证的事实").first()).toBeVisible();
});

test("public deterministic cooling demo exposes only valid action-link schemes", async ({ page }) => {
  await page.goto("/tokyo");
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("tokyo-example-cooling").click();
  await expect(page.getByTestId("tokyo-selected-location")).toContainText("Koto City");
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({ timeout: 60_000 });

  const sourceUrl = await captureExternalOpen(page, "tokyo-source-");
  expect(sourceUrl).toMatch(/^https:\/\//);

  const directionsUrl = await captureExternalOpen(page, "tokyo-directions-");
  expect(directionsUrl).toMatch(/^https:\/\/www\.google\.com\/maps\/search/);

  const websiteUrl = await captureExternalOpen(page, "tokyo-website-");
  if (websiteUrl !== null) {
    expect(websiteUrl).toMatch(/^https:\/\//);
  }

  const phoneUrl = await captureExternalOpen(page, "tokyo-call-");
  if (phoneUrl !== null) {
    expect(phoneUrl).toMatch(/^tel:/);
  }
});
