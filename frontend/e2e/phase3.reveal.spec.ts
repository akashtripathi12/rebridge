import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

test.describe("Phase 3 — the grading reveal", () => {
  test("full staged sequence over a real poll", async ({ page }, info) => {
    await page.goto("/reveal");

    // Scanning phase: scan line visible, status not done, CTA disabled.
    await expect(page.getByTestId("scan-line")).toBeVisible();
    const cta = page.getByTestId("list-cta");
    await expect(cta).toBeDisabled();
    await page.screenshot({
      path: `${SHOTS}/phase3-scanning-${info.project.name}.png`,
    });

    // Grade lands (poll resolves) -> stamp + confidence + pins.
    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("defect-pin").first()).toBeVisible();
    const pins = await page.getByTestId("defect-pin").count();
    expect(pins).toBeGreaterThanOrEqual(1);
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();

    // Receipt prints, with the economics rows in order + the route line.
    const receipt = page.getByTestId("receipt");
    await expect(receipt).toBeVisible();
    await expect(receipt).toContainText("Resale value");
    await expect(receipt).toContainText("Margin");
    await expect(receipt).toContainText(/buyers < 5 km/);

    // CTA enables only at the end, carrying the amber price.
    await expect(cta).toBeEnabled({ timeout: 10000 });
    await expect(cta).toContainText("List for");
    await expect(cta.locator('[data-price="amber"]')).toBeVisible();

    await page.screenshot({
      path: `${SHOTS}/phase3-revealed-${info.project.name}.png`,
      fullPage: true,
    });
  });

  test("reduced-motion collapses to the final state", async ({ browser }) => {
    const ctx = await browser.newContext({ reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto("/reveal");
    // No scan animation; result still resolves and CTA enables.
    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("list-cta")).toBeEnabled({ timeout: 10000 });
    await expect(page.getByTestId("receipt")).toContainText("Margin");
    await ctx.close();
  });
});
