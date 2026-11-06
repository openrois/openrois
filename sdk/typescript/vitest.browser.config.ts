import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/conformance.test.ts"],
    globalSetup: ["tests/conformance.setup.ts"],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [{ browser: "chromium" }],
      // A failed scenario explains itself in text, and a picture of an empty page does not.
      screenshotFailures: false,
    },
  },
});
