import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/rois-client.ts", "src/jsonrpc.ts", "src/transport.ts"],
  format: ["esm", "cjs"],
  dts: true,
  clean: true,
  target: "es2022",
  outDir: "dist",
  sourcemap: true,
  // Bundle @openrois/interfaces into the SDK output so the SDK is
  // self-contained. The interfaces package's compiled JS uses extensionless
  // imports that Node.js ESM cannot resolve. Bundling avoids that issue.
  noExternal: ["@openrois/interfaces"],
});