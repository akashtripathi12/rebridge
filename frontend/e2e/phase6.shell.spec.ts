import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

test.describe("Phase 6 — hero + notification + review console", () => {
  test("hero renders, type reveal composes, journey loop runs", async ({
    page,
  }, info) => {
    await page.goto("/");
    const headline = page.getByTestId("hero-headline");
    await expect(headline).toBeVisible();
    await expect(headline).toContainText("next owner");

    // Type reveal resolves to the composed state (spans end fully visible).
    const lastSpan = headline.locator("[data-line] > span").last();
    await expect
      .poll(async () => lastSpan.evaluate((el) => getComputedStyle(el).opacity))
      .toBe("1");

    await expect(page.getByTestId("journey-loop")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/phase6-hero-${info.project.name}.png`, fullPage: true });
  });

  test("hero reduced-motion collapses cleanly", async ({ browser }) => {
    const ctx = await browser.newContext({ reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto("/");
    const lastSpan = page
      .getByTestId("hero-headline")
      .locator("[data-line] > span")
      .last();
    await expect(lastSpan).toBeVisible();
    expect(await lastSpan.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    await expect(page.getByTestId("journey-graded")).toBeVisible();
    await ctx.close();
  });

  test("notification renders both variants", async ({ page }, info) => {
    await page.goto("/notifications");
    const notifs = page.getByTestId("notification");
    await expect(notifs).toHaveCount(2);
    await expect(page.locator('[data-variant="seller"]')).toBeVisible();
    await expect(page.locator('[data-variant="buyer"]')).toBeVisible();
    await expect(
      page.locator('[data-variant="seller"]').getByTestId("notif-detail"),
    ).toContainText("buyers < 5 km");
    await page.screenshot({
      path: `${SHOTS}/phase6-notifications-${info.project.name}.png`,
      fullPage: true,
    });
  });

  test("review console: priority sort + override mutates the row", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "desktop", "operator tool — desktop");
    await page.goto("/review");
    await expect(page.getByTestId("review-table")).toBeVisible();
    const rows = page.getByTestId("review-row");
    expect(await rows.count()).toBeGreaterThanOrEqual(3);

    // Sorted by priority: the lowest-confidence item (HIGH) is first.
    await expect(rows.first().getByTestId("priority-tag")).toHaveText("High");

    await page.screenshot({ path: `${SHOTS}/phase6-review.png`, fullPage: true });

    // Override the first row → it mutates to the resolved/overridden state.
    await rows.first().getByTestId("override-select").selectOption("Very Good");
    await rows.first().getByTestId("override-btn").click();
    await expect(rows.first().getByTestId("row-resolution")).toContainText(
      "Overridden → Very Good",
    );
  });
});
