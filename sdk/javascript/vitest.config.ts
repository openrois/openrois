import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

/**
 * With OPENROIS_SDK_PACKAGE naming an unpacked tarball, the tests import its build in place
 * of the sources. The release workflow runs the conformance list this way, so that the list
 * covers the file that goes to npm.
 */
const sdkPackage = process.env.OPENROIS_SDK_PACKAGE;
export const sdkAlias = sdkPackage
  ? [
      {
        find: /^\.\.\/src\/(rois-client|transport)$/,
        replacement: `${resolve(sdkPackage)}/dist/$1.js`,
      },
    ]
  : [];

export default defineConfig({
  resolve: { alias: sdkAlias },
  test: {
    include: ["tests/**/*.test.ts"],
    globalSetup: ["tests/conformance.setup.ts"],
    // Files that reach a gateway share its components, so a bind in one would refuse a
    // bind in another.
    fileParallelism: false,
  },
});
