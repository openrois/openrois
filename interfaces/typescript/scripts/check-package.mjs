/**
 * Prove that the built package loads in plain Node.js.
 *
 * The vitest suite runs on the sources through Vite, which resolves imports that Node.js
 * refuses, so it cannot see a package that fails to load. This script runs on `dist/` with
 * nothing in between. The package imports itself by name, so `exports` decides what loads,
 * as it does for a user.
 *
 * Usage:
 *   npm run build && npm run test:package
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
const require = createRequire(import.meta.url);

for (const subpath of Object.keys(manifest.exports)) {
  const specifier = subpath === "." ? manifest.name : `${manifest.name}/${subpath.slice(2)}`;
  const imported = await import(specifier);
  const required = require(specifier);
  assert.ok(Object.keys(imported).length > 0, `${specifier} exports nothing`);
  // One build serves both, so a schema object must be the same object either way.
  assert.deepEqual(Object.keys(required), Object.keys(imported));
  for (const name of Object.keys(imported)) {
    assert.equal(required[name], imported[name], `${specifier} has two copies of ${name}`);
  }
}

const root = await import("@openrois/interfaces");
const components = await import("@openrois/interfaces/components");
const condition = await import("@openrois/interfaces/condition");
const values = await import("@openrois/interfaces/values");

assert.equal(root.ResultSchema.parse({ name: "n", data_type_ref: "int", value: "3" }).value, "3");
assert.equal(condition.eq("component_ref", "it's"), "component_ref = 'it''s'");
assert.equal(values.encodeValue("float", 2), "2.0");
assert.deepEqual(values.decodeValue("int[]", "[1, 2]"), [1, 2]);
assert.equal(Object.keys(components).filter((name) => name.endsWith("_PROFILE")).length, 18);
assert.ok(components.ReactionStatusResultSchema);

console.log(`${manifest.name} ${manifest.version} loads in Node.js ${process.version}`);
