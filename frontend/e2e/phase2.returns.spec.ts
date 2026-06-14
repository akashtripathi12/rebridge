import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

// A tiny valid PNG (1x1) used as the uploaded photo bytes.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
const file = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });

test.describe("Phase 2 — Returns Desk + async grade", () => {
  test("upload → grade → poll resolves → grade + confidence render", async ({
    page,
  }, info) => {
    await page.goto("/returns");

    // Grade disabled until 2+ photos.
    await expect(page.getByTestId("grade-btn")).toBeDisabled();

    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);

    // Batch strip shows the captured thumbnails.
    await expect(page.getByTestId("thumb")).toHaveCount(2);
    const grade = page.getByTestId("grade-btn");
    await expect(grade).toBeEnabled();
    await page.screenshot({
      path: `${SHOTS}/phase2-capture-${info.project.name}.png`,
    });

    await grade.click();

    // Async poll resolves -> the in-place reveal shows grade + confidence + receipt.
    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();
    await expect(page.getByTestId("receipt")).toContainText("Margin");
    await page.screenshot({
      path: `${SHOTS}/phase2-graded-${info.project.name}.png`,
    });
  });

  test("blurry capture → RETAKE_REQUIRED → retake state", async ({ page }, info) => {
    await page.goto("/returns");
    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);
    await page.getByTestId("sim-blurry").check();
    await page.getByTestId("grade-btn").click();

    const retake = page.getByTestId("retake-state");
    await expect(retake).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("retake-btn")).toBeVisible();
    await page.screenshot({
      path: `${SHOTS}/phase2-retake-${info.project.name}.png`,
    });

    // Retake resets back to capture.
    await page.getByTestId("retake-btn").click();
    await expect(page.getByTestId("grade-btn")).toBeDisabled();
  });
});
