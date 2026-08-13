import { expect, test, type Page } from "@playwright/test";

const EN_QUERY = "I need a nearby clinic in Tokyo where staff can support me in English.";
const JA_QUERY = "とても暑いので、近くの指定クーリングシェルターを探したいです。";
const ZH_QUERY = "我在育儿方面遇到困难，但不知道应该联系东京的哪种公共支持服务。";

async function chooseManualLocation(page: Page, municipality: string) {
  await page.getByTestId("tokyo-manual-location").fill(municipality);
  await page.getByTestId("tokyo-use-manual-location").click();
  const selectedLocation = page.getByTestId("tokyo-selected-location");
  await expect(selectedLocation).toContainText(municipality);
}

async function search(page: Page, query: string, municipality: string) {
  await page.getByTestId("tokyo-query").fill(query);
  await chooseManualLocation(page, municipality);
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({
    timeout: 60_000,
  });

  const resource = page.locator('[data-testid^="tokyo-resource-"]').first();
  const source = page.locator('[data-testid^="tokyo-source-"]').first();
  await expect(resource).toBeVisible();
  await expect(source).toBeVisible();
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
  return page.evaluate(() => {
    return window.sessionStorage.getItem("carepath-cp208-open-url");
  });
}

test("public Tokyo multilingual journeys", async ({ page }) => {
  await page.goto("/tokyo");
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("account-privacy-panel")).toHaveCount(0);
  await expect(page).toHaveURL(/\/tokyo\/?$/);

  await page.reload();
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page).toHaveURL(/\/tokyo\/?$/);

  await page.getByTestId("tokyo-language-en").click();
  await search(page, EN_QUERY, "新宿区");
  const enFacts = page.getByText("Verified source facts").first();
  await expect(enFacts).toBeVisible();

  await page.getByTestId("tokyo-language-ja").click();
  await search(page, JA_QUERY, "江東区");
  const jaFacts = page.getByText("確認済みの出典情報").first();
  await expect(jaFacts).toBeVisible();

  await page.getByTestId("tokyo-language-zh").click();
  await search(page, ZH_QUERY, "江東区");
  const zhFacts = page.getByText("经来源验证的事实").first();
  await expect(zhFacts).toBeVisible();
});

test("public cooling demo action links", async ({ page }) => {
  await page.goto("/tokyo");
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({
    timeout: 60_000,
  });
  await page.getByTestId("tokyo-example-cooling").click();
  const selectedLocation = page.getByTestId("tokyo-selected-location");
  await expect(selectedLocation).toContainText("Koto City");
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({
    timeout: 60_000,
  });

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
