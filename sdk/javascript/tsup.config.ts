import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/rois-client.ts", "src/transport.ts"],
  format: ["esm"],
  // A `/// <reference lib>` in the source does not survive the d.ts bundling. The client
  // declares Symbol.asyncDispose, so a consumer with the default lib needs this one.
  dts: { banner: '/// <reference lib="esnext.disposable" />' },
  clean: true,
  target: "es2022",
  outDir: "dist",
  sourcemap: true,
});
