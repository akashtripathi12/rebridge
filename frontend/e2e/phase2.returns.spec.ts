import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

// A tiny valid PNG (1x1) used as the uploaded photo bytes.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
const file = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });

test.describe("Phase 2 — Returns Desk + async grade (folded into scan)", () => {
  test("upload → grade → folded scan → reveal renders grade + confidence", async ({
    page,
  }, info) => {
    await page.goto("/returns");

    await expect(page.getByTestId("grade-btn")).toBeDisabled();
    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);
    await expect(page.getByTestId("thumb")).toHaveCount(2);
    const grade = page.getByTestId("grade-btn");
    await expect(grade).toBeEnabled();
    await page.screenshot({
      path: `${SHOTS}/phase2-capture-${info.project.name}.png`,
    });

    await grade.click();

    // Folds into the 3D inspection beat, then auto-advances to the verdict.
    await expect(page).toHaveURL(/\/scanner\?item=/, { timeout: 10000 });
    await expect(page).toHaveURL(/\/reveal\?item=/, { timeout: 25000 });

    await expect(page.getByTestId("grade-stamp")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();
    await expect(page.getByTestId("receipt")).toContainText("Margin");
    await page.screenshot({
      path: `${SHOTS}/phase2-graded-${info.project.name}.png`,
    });
  });

  test("blurry capture → folded scan surfaces RETAKE_REQUIRED", async ({
    page,
  }, info) => {
    await page.goto("/returns");
    await page
      .getByTestId("file-input")
      .setInputFiles([file("front.png"), file("side.png")]);
    await page.getByTestId("sim-blurry").check();
    await page.getByTestId("grade-btn").click();

    await expect(page).toHaveURL(/\/scanner\?item=/, { timeout: 10000 });
    const retake = page.getByTestId("scanner-retake");
    await expect(retake).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("scanner-retake-btn")).toBeVisible();
    await page.screenshot({
      path: `${SHOTS}/phase2-retake-${info.project.name}.png`,
    });

    // Retake bounces back to capture.
    await page.getByTestId("scanner-retake-btn").click();
    await expect(page).toHaveURL(/\/returns/);
    await expect(page.getByTestId("grade-btn")).toBeDisabled();
  });
});
