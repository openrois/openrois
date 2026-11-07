import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    globalSetup: ["tests/conformance.setup.ts"],
    // Files that reach a gateway share its components, so a bind in one would refuse a
    // bind in another.
    fileParallelism: false,
  },
});
