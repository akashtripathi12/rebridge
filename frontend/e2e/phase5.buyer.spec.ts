import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

test.describe("Phase 5 — buyer flow (Rahul + marketplace + Health Card)", () => {
  test("marketplace renders routed items with grade/price/distance + filter", async ({
    page,
  }, info) => {
    await page.goto("/market");

    // The persona's proactive routed match renders.
    await expect(page.getByTestId("match-push")).toBeVisible();

    // At least one routed item with grade + price + distance + intent.
    const cards = page.getByTestId("market-card");
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(1);
    await expect(cards.first().getByTestId("market-distance")).toContainText("km");
    await expect(cards.first().locator("[data-grade-badge]")).toBeVisible();
    await expect(cards.first().locator('[data-price="amber"]')).toBeVisible();
    await expect(cards.first().getByTestId("market-intent")).toBeVisible();

    await page.screenshot({
      path: `${SHOTS}/phase5-market-${info.project.name}.png`,
      fullPage: true,
    });

    // Category filter narrows the grid (Books has exactly 1 seeded item).
    await page.getByTestId("cat-books").click();
    await expect(page.getByTestId("market-card")).toHaveCount(1);
    await page.getByTestId("cat-all").click();
    expect(await page.getByTestId("market-card").count()).toBeGreaterThanOrEqual(3);
  });

  test("Rahul match → Health Card with grade/confidence/defects/QR", async ({
    page,
  }, info) => {
    await page.goto("/market");

    // Deterministic: the persona's routed push opens its Health Card.
    await page.getByTestId("match-push").click();
    await expect(page).toHaveURL(/\/card\/itm_shoe7/);

    const hc = page.getByTestId("health-card");
    await expect(hc).toBeVisible();
    await expect(hc.locator("[data-grade-badge]")).toBeVisible();
    await expect(page.getByTestId("verified-badge")).toBeVisible();
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();
    // Defects (toe/sole) listed as findings.
    await expect(page.getByTestId("findings")).toContainText(/toe|sole/);
    // A real QR encoding the card URL.
    const qr = page.getByTestId("qr");
    await expect(qr).toBeVisible();
    await expect(qr.locator("svg")).toBeVisible();
    expect(await qr.getAttribute("data-qr-value")).toContain("/card/itm_shoe7");

    await page.screenshot({
      path: `${SHOTS}/phase5-healthcard-${info.project.name}.png`,
      fullPage: true,
    });

    // Reserve completes the buyer narrative.
    await page.getByTestId("reserve-btn").click();
    await expect(page.getByTestId("reserved-banner")).toBeVisible();
  });
});
