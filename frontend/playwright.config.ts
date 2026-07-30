import { defineConfig, devices } from "@playwright/test";

const viewports = {
  "desktop-1440": { width: 1440, height: 1000 },
  "desktop-1024": { width: 1024, height: 900 },
  "tablet-768": { width: 768, height: 1024 },
  "mobile-390": { width: 390, height: 844 }
};

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.002
    }
  },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173",
    colorScheme: "light",
    locale: "ru-RU",
    timezoneId: "Europe/Moscow",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/design-system",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  },
  projects: [
    ...Object.entries(viewports).map(([name, viewport]) => ({
      name,
      use: { viewport, colorScheme: "light" as const }
    })),
    ...Object.entries(viewports).map(([name, viewport]) => ({
      name: `dark-${name}`,
      use: { viewport, colorScheme: "dark" as const }
    }))
  ]
});
