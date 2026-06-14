import { test } from "@playwright/test";
import { expectAmberDiscipline } from "./helpers";

/**
 * Build-wide amber discipline: no route may put amber on a chrome button. (Price
 * numbers, the receipt route value, the scan beam, and dark-stage product
 * accents are allowed — those aren't buttons.) Re-runs every phase as a guard.
 */
const ROUTES = [
  "/",
  "/styleguide",
  "/returns",
  "/reveal",
  "/scanner",
  "/market",
  "/card/itm_shoe7",
  "/notifications",
  "/review",
];

for (const route of ROUTES) {
  test(`amber discipline — ${route}`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "audit once, on desktop");
    await page.goto(route);
    await page.waitForTimeout(500);
    await expectAmberDiscipline(page);
  });
}
