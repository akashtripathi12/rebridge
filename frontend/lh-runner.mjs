// One-off Lighthouse runner: launches Chromium via Playwright (which has exec
// perms on this box), then runs Lighthouse over the CDP port for each URL.
import { chromium } from "playwright-core";
import lighthouse from "lighthouse";

const urls = process.argv.slice(2);
const browser = await chromium.launch({
  headless: true,
  args: ["--remote-debugging-port=9222", "--no-sandbox", "--disable-gpu"],
});
try {
  for (const url of urls) {
    const result = await lighthouse(
      url,
      { port: 9222, onlyCategories: ["performance"], output: "json", logLevel: "error" },
    );
    const score = Math.round(result.lhr.categories.performance.score * 100);
    console.log(`PERF ${url} = ${score}`);
  }
} finally {
  await browser.close();
}
