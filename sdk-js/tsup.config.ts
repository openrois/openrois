import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/jsonrpc.ts"],
  format: ["esm", "cjs"],
  dts: true,
  clean: true,
  target: "es2022",
  outDir: "dist",
  sourcemap: true,
});