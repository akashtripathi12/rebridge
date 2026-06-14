import { test, expect, type ConsoleMessage } from "@playwright/test";
import { SHOTS } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
const file = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });

/**
 * The golden path is ONE item, start to finish. From the hero, one click grades a
 * real returned item, prices it, routes it, and reserves it for a nearby buyer —
 * the SAME item id at the reveal, as the pinned top marketplace match, and on the
 * Health Card. Fails on any console error or a context break (cold screen / dead
 * end). Run with --repeat-each=5 for the consecutive-runs gate.
 */
test.describe("Golden path — one item, hero → reserved", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "chromium only");

  test("same item threads capture → scan → reveal → market → card → reserve", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "desktop", "demo runs desktop");

    const errors: string[] = [];
    page.on("console", (m: ConsoleMessage) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push(String(e)));

    const shot = (n: string) =>
      info.repeatEachIndex === 0
        ? page.screenshot({ path: `${SHOTS}/golden-${n}.png`, fullPage: true })
        : Promise.resolve(Buffer.from(""));

    // 1. Hero — one way in.
    await page.goto("/");
    await expect(page.getByTestId("hero-headline")).toContainText("next owner");
    await shot("1-hero");
    await page.getByTestId("start-journey").click();
    await expect(page).toHaveURL(/\/returns/);

    // 2. Capture → Grade (starts the journey).
    await expect(page.getByTestId("journey-rail")).toBeVisible();
    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);
    await expect(page.getByTestId("thumb")).toHaveCount(2);
    await shot("2-capture");
    await page.getByTestId("grade-btn").click();

    // 3. Folded inspection beat (scanner), threading ?item.
    await expect(page).toHaveURL(/\/scanner\?item=([^&]+)/, { timeout: 10000 });
    const itemId = new URL(page.url()).searchParams.get("item")!;
    expect(itemId).toBeTruthy();
    await shot("3-scan");

    // 4. Verdict (reveal) — SAME item id.
    await expect(page).toHaveURL(new RegExp(`/reveal\\?item=${itemId}`), {
      timeout: 25000,
    });
    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("receipt")).toContainText(/buyers < 5 km/);
    const list = page.getByTestId("list-cta");
    await expect(list).toBeEnabled({ timeout: 10000 });
    await shot("4-reveal");
    await list.click();

    // 5. Routing moment → follow to buyer.
    await expect(page).toHaveURL(/\/notifications\?flow=1/);
    await expect(page.locator('[data-variant="seller"]')).toBeVisible();
    await shot("5-routing");
    await page.getByTestId("follow-to-buyer").click();

    // 6. Marketplace — the demo item is the pinned top match (same id).
    await expect(page).toHaveURL(/\/market/);
    const push = page.getByTestId("match-push");
    await expect(push).toBeVisible();
    await expect(push).toHaveAttribute("href", new RegExp(`/card/${itemId}`));
    await shot("6-market");
    await push.click();

    // 7. Health Card — SAME item id, verified.
    await expect(page).toHaveURL(new RegExp(`/card/${itemId}`));
    await expect(page.getByTestId("health-card")).toBeVisible();
    await expect(page.getByTestId("verified-badge")).toBeVisible();
    await expect(page.getByTestId("qr")).toHaveAttribute(
      "data-qr-value",
      new RegExp(`/card/${itemId}`),
    );
    await shot("7-card");

    // 8. Reserve → confirmation → back to hero (no dead end).
    await page.getByTestId("reserve-btn").click();
    await expect(page.getByTestId("confirmation")).toBeVisible();
    await shot("8-confirmation");
    await page.getByTestId("back-to-hero").click();
    await expect(page.getByTestId("hero-headline")).toBeVisible();

    expect(errors, `console errors: ${errors.join(" | ")}`).toEqual([]);
  });
});
