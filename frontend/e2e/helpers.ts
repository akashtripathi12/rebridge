import { Page, expect } from "@playwright/test";

export const SHOTS = "e2e/__screenshots__";

/** Assert the three brand fonts actually loaded (not fallback). */
export async function expectFontsLoaded(page: Page) {
  const fonts = await page.evaluate(async () => {
    await (document as any).fonts.ready;
    const fams = new Set<string>();
    (document as any).fonts.forEach((f: FontFace) => fams.add(f.family));
    return Array.from(fams);
  });
  const joined = fonts.join(" ");
  expect(joined).toContain("Archivo");
  expect(joined).toContain("Manrope");
  expect(joined.toLowerCase()).toContain("jetbrains");
}

/**
 * Amber audit (v2 rule): #FF9900 / amber-deep may appear only on price numbers,
 * the receipt route value, the scan beam, and dark-stage product accents — NEVER
 * as a button/header/nav background or icon fill in app chrome. We assert no
 * element with a primary-action role carries an amber background.
 */
export async function expectAmberDiscipline(page: Page) {
  const violations = await page.evaluate(() => {
    const amber = ["rgb(255, 153, 0)", "rgb(217, 122, 0)"];
    const bad: string[] = [];
    document.querySelectorAll("button").forEach((el) => {
      const bg = getComputedStyle(el).backgroundColor;
      // hero "amber" variant is allowed; flag only primary/secondary chrome.
      if (amber.includes(bg) && !el.hasAttribute("data-amber-ok")) {
        bad.push("button:" + (el.textContent || "").trim().slice(0, 20));
      }
    });
    return bad;
  });
  expect(violations, `amber on chrome: ${violations.join(", ")}`).toEqual([]);
}
