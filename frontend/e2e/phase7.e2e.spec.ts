import { test, expect, type ConsoleMessage } from "@playwright/test";
import { SHOTS } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
const file = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });

/**
 * Phase 7 — the full scripted demo path, end to end, headless. Run this with
 * --repeat-each=5 for the 5-consecutive-green-runs gate. Fails on ANY console
 * error or page error along the way (no overclaim, no broken state).
 */
test.describe("Phase 7 — end-to-end demo path", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "chromium only");

  test("hero → returns → reveal → list → market → health card → scan → review", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "desktop", "demo runs desktop");

    const errors: string[] = [];
    page.on("console", (m: ConsoleMessage) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push(String(e)));

    // 1. Hero
    await page.goto("/");
    await expect(page.getByTestId("hero-headline")).toContainText("next owner");
    await page.getByRole("link", { name: "Watch the demo" }).click();
    await expect(page).toHaveURL(/\/returns/);

    // 2. Returns Desk capture → grade
    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);
    await expect(page.getByTestId("thumb")).toHaveCount(2);
    await page.getByTestId("grade-btn").click();

    // 3. Grade reveal resolves
    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("receipt")).toContainText("Margin");
    const list = page.getByTestId("list-cta");
    await expect(list).toBeEnabled({ timeout: 10000 });

    // 4. List → marketplace
    await list.click();
    await expect(page).toHaveURL(/\/market/);
    await expect(page.getByTestId("match-push")).toBeVisible();

    // 5. Routed match → Health Card → reserve
    await page.getByTestId("match-push").click();
    await expect(page).toHaveURL(/\/card\/itm_shoe7/);
    await expect(page.getByTestId("health-card")).toBeVisible();
    await expect(page.getByTestId("verified-badge")).toBeVisible();
    await page.getByTestId("reserve-btn").click();
    await expect(page.getByTestId("reserved-banner")).toBeVisible();

    // 6. 3D scan
    await page.goto("/scanner");
    await page.getByTestId("scanner-grade-btn").click();
    await expect(page.getByTestId("scanner-grade")).toBeVisible({ timeout: 15000 });
    expect(await page.getByTestId("hotspot").count()).toBeGreaterThanOrEqual(2);

    // 7. Review console
    await page.goto("/review");
    await page.getByTestId("review-row").first().getByTestId("confirm-btn").click();
    await expect(
      page.getByTestId("review-row").first().getByTestId("row-resolution"),
    ).toContainText("Confirmed");

    if (info.repeatEachIndex === 0) {
      await page.screenshot({ path: `${SHOTS}/phase7-demo-end.png`, fullPage: true });
    }

    expect(errors, `console errors: ${errors.join(" | ")}`).toEqual([]);
  });
});
