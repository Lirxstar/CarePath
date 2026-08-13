import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const outputDir = path.resolve(process.cwd(), "../../submission/tokyo/screenshots");

async function ready(page: Page) {
  await page.goto("/tokyo");
  await expect(page.getByTestId("tokyo-screen")).toBeVisible({ timeout: 60_000 });
  fs.mkdirSync(outputDir, { recursive: true });
}

async function manualLocation(page: Page, municipality: string) {
  await page.getByTestId("tokyo-manual-location").fill(municipality);
  await page.getByTestId("tokyo-use-manual-location").click();
  await expect(page.getByTestId("tokyo-selected-location")).toContainText(municipality);
}

test("capture CP-209 submission screenshots from public Tokyo", async ({ page }) => {
  await ready(page);
  await page.getByTestId("tokyo-language-en").click();
  await page.screenshot({
    path: path.join(outputDir, "01-tokyo-landing-en.png"),
    fullPage: true,
  });

  await page.getByTestId("tokyo-example-cooling").click();
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-testid^="tokyo-resource-"]').first()).toBeVisible();
  await page.screenshot({
    path: path.join(outputDir, "02-koto-cooling-results-en.png"),
    fullPage: true,
  });

  await page.getByTestId("tokyo-language-zh").click();
  await page.getByTestId("tokyo-query").fill(
    "我在育儿方面遇到困难，但不知道应该联系东京的哪种公共支持服务。",
  );
  await manualLocation(page, "江東区");
  await page.getByTestId("tokyo-search").click();
  await expect(page.getByTestId("tokyo-results")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("经来源验证的事实").first()).toBeVisible();
  await page.screenshot({
    path: path.join(outputDir, "03-family-support-results-zh.png"),
    fullPage: true,
  });
});
