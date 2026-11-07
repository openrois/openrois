import { builtinModules } from "node:module";
import { defineConfig } from "vite";

const NODE_ONLY = new Set([...builtinModules, "ws"]);

export default defineConfig({
  plugins: [
    {
      // Vite swaps a Node.js module for an empty stub and only warns, so the build would
      // pass and the page would break when it loads.
      name: "refuse-node-modules",
      enforce: "pre",
      resolveId(source) {
        if (source.startsWith("node:") || NODE_ONLY.has(source)) {
          this.error(`${source} cannot load in a browser`);
        }
      },
    },
  ],
});
