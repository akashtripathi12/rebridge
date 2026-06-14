import { test, expect } from "@playwright/test";
import { SHOTS, expectFontsLoaded, expectAmberDiscipline } from "./helpers";

test.describe("Phase 1 — foundation & component kit", () => {
  test("styleguide renders every core component", async ({ page }, info) => {
    await page.goto("/styleguide");
    await expect(
      page.getByRole("heading", { name: "Component styleguide" }),
    ).toBeVisible();

    // Core components present.
    await expect(page.getByTestId("receipt")).toBeVisible();
    await expect(page.getByTestId("match-chip").first()).toBeVisible();
    await expect(page.getByTestId("priority-tag").first()).toBeVisible();
    await expect(page.getByTestId("status-line").first()).toBeVisible();
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();

    // All five grade badges render, all on a black chip.
    const badges = page.locator("[data-grade-badge]");
    await expect(badges).toHaveCount(8); // 5 grades + 3 size demos
    for (const text of ["Like New", "Very Good", "Good", "Acceptable", "Unsellable"]) {
      await expect(badges.filter({ hasText: text }).first()).toBeVisible();
    }

    // Price uses amber-deep; confidence/ids are mono.
    const price = page.locator('[data-price="amber"]').first();
    const priceColor = await price.evaluate(
      (el) => getComputedStyle(el).color,
    );
    expect(priceColor).toBe("rgb(217, 122, 0)"); // --amber-deep

    await expectFontsLoaded(page);
    await expectAmberDiscipline(page);

    await page.screenshot({
      path: `${SHOTS}/phase1-styleguide-${info.project.name}.png`,
      fullPage: true,
    });
  });

  test("status line reaches done state (trust green)", async ({ page }) => {
    await page.goto("/styleguide");
    const done = page.locator('[data-testid="status-line"][data-done="true"]');
    await expect(done.first()).toBeVisible();
    // Both done lines are trust-green, not amber.
    const color = await done.first().locator("span").last().evaluate(
      (el) => getComputedStyle(el).color,
    );
    expect(color).toBe("rgb(0, 125, 72)"); // --trust
  });
});
