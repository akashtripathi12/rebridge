import { test, expect } from "@playwright/test";
import { SHOTS } from "./helpers";

// 3D is heavy; run desktop only for this gate.
test.describe("Phase 4 — 3D product scanner", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "chromium only");

  test("mounts, scans, reveals hotspots + grade (WebGL fallback)", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "desktop", "desktop only");
    await page.goto("/scanner");

    // Canvas mounts with a live WebGL context (no black canvas).
    const canvas = page.locator('[data-testid="scanner"] canvas');
    await expect(canvas).toBeVisible();
    const gl = await canvas.evaluate((c: HTMLCanvasElement) => {
      const ctx =
        c.getContext("webgl2") || c.getContext("webgl");
      return ctx ? (ctx as WebGLRenderingContext).drawingBufferWidth : 0;
    });
    expect(gl).toBeGreaterThan(0);

    // Headless => no WebGPU => capability badge shows the WebGL fallback.
    await expect(page.getByText(/GPU:\s*WebGL2/)).toBeVisible();

    await page.waitForTimeout(800); // let auto-rotate settle
    await page.screenshot({ path: `${SHOTS}/phase4-idle.png` });

    // Grade -> sweep -> hotspots pop -> grade badge + confidence.
    await page.getByTestId("scanner-grade-btn").click();
    await expect(page.getByTestId("scanner-grade")).toBeVisible({ timeout: 15000 });
    const hotspots = page.getByTestId("hotspot");
    await expect(hotspots.first()).toBeVisible({ timeout: 10000 });
    expect(await hotspots.count()).toBeGreaterThanOrEqual(2);
    await expect(page.getByTestId("confidence-value").first()).toBeVisible();

    // Canvas isn't a black void: read a grid of pixels from the live GL buffer
    // and require some brightness (the lit product + amber rim).
    const brightness = await canvas.evaluate((c: HTMLCanvasElement) => {
      const gl = (c.getContext("webgl2") ||
        c.getContext("webgl")) as WebGLRenderingContext;
      const w = gl.drawingBufferWidth;
      const h = gl.drawingBufferHeight;
      const px = new Uint8Array(w * h * 4);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      let max = 0;
      for (let i = 0; i < px.length; i += 4) {
        const lum = px[i] + px[i + 1] + px[i + 2];
        if (lum > max) max = lum;
      }
      return max;
    });
    expect(brightness).toBeGreaterThan(60); // lit product, not a black canvas

    await page.screenshot({ path: `${SHOTS}/phase4-scanned.png` });

    // Replay control present after grading.
    await expect(page.getByTestId("scanner-replay")).toBeVisible();
  });

  test("renders offscreen without crashing (demand/pause)", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "desktop", "desktop only");
    await page.goto("/scanner");
    await expect(page.locator('[data-testid="scanner"] canvas')).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(400);
    // No uncaught errors; canvas element still attached.
    await expect(page.locator('[data-testid="scanner"] canvas')).toBeAttached();
  });
});
