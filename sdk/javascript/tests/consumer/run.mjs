/**
 * The four checks of a consumer on the packed tarball: Node ESM, Node require, tsc under
 * nodenext, and a Vite browser build. What a consumer installs can differ from what the
 * tests import, so these run on `npm pack` output in a clean folder outside the repository.
 * The folder holds only tests/consumer/project and what npm installs for the tarball.
 *
 * Run it from sdk/javascript after a build, which `npm run test:consumer` does. TMPDIR
 * sets where the folder goes. It exits with 0 when all four pass.
 */

import { execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SDK = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const PROJECT = fileURLToPath(new URL("./project", import.meta.url));

const folder = mkdtempSync(join(tmpdir(), "openrois-sdk-consumer-"));

function run(command, args, cwd = folder) {
  console.log(`\n$ ${command} ${args.join(" ")}`);
  return execFileSync(command, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] });
}

function pack() {
  const [{ filename }] = JSON.parse(run("npm", ["pack", "--json", "--pack-destination", folder], SDK));
  return join(folder, filename);
}

function install(tarball) {
  const { devDependencies } = JSON.parse(readFileSync(join(SDK, "package.json"), "utf8"));
  cpSync(PROJECT, folder, { recursive: true });
  writeFileSync(
    join(folder, "package.json"),
    JSON.stringify({ name: "consumer", private: true, type: "module" }),
  );
  run("npm", [
    "install",
    "--no-audit",
    "--no-fund",
    tarball,
    `typescript@${devDependencies.typescript}`,
    `vite@${devDependencies.vite}`,
  ]);
}

console.log(`Consumer folder: ${folder}`);
install(pack());
console.log(run("node", ["esm.mjs"]));
console.log(run("node", ["require.cjs"]));
run("npx", ["tsc", "--noEmit"]);
run("npx", ["vite", "build", "--logLevel", "warn"]);
console.log("\nAll four consumer checks passed.");
