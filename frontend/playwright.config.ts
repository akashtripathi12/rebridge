import { defineConfig, devices } from "@playwright/test";

/**
 * Durable gate specs. Each phase has e2e/phaseN.*.spec.ts. A gate is GREEN only
 * when its spec passes headless. The dev server is auto-started and reused.
 * Screenshots land in e2e/__screenshots__ and are referenced from PROGRESS.md.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "off",
    // Force software GL so WebGL works headless (no real GPU) — this is the
    // "WebGPU disabled → WebGL fallback" path the Phase 4 gate verifies.
    launchOptions: {
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist",
      ],
    },
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 5"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
