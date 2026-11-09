import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The footer names the SDK version the page is built with.
const sdk = JSON.parse(readFileSync(new URL("../../sdk/javascript/package.json", import.meta.url), "utf8")) as {
  version: string;
};

export default defineConfig({
  plugins: [react()],
  define: {
    __SDK_VERSION__: JSON.stringify(sdk.version),
  },
});
