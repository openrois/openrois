/**
 * Global setup of the conformance suite. It runs in Node.js in both modes and hands the
 * URLs to tests/conformance.test.ts through `provide`, because a browser has no
 * process.env for the test file to read.
 *
 * With OPENROIS_GATEWAY_URL set, it starts testing/conformance/scripted_server.py with
 * `python3`, which needs the websockets package, and stops it when the run ends. Without
 * it, the suite is skipped in Node.js. A browser run fails instead, because that run
 * exists only for this suite, and a skipped suite would pass with nothing proven.
 */

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    /** The gateway with the mock adapter behind it. Empty when no stack was named. */
    gatewayUrl: string;
    /** The engine id of the mock adapter, the first part of every ref. */
    engineId: string;
    /** The scripted server, without a path. Empty when no stack was named. */
    scriptedUrl: string;
  }
}

const SCRIPTED_SERVER = fileURLToPath(
  new URL("../../../testing/conformance/scripted_server.py", import.meta.url),
);

/** Start the scripted server, and return its URL and how to stop it. */
function startScriptedServer(): Promise<{ url: string; stop: () => Promise<void> }> {
  const server = spawn("python3", [SCRIPTED_SERVER], { stdio: ["ignore", "pipe", "pipe"] });
  const errors: string[] = [];
  server.stderr.on("data", (chunk) => errors.push(String(chunk)));
  const exited = new Promise<void>((resolve) => server.once("close", () => resolve()));

  const stop = async () => {
    server.kill();
    await exited;
  };

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    // The first line of the server is the port it bound.
    createInterface({ input: server.stdout }).once("line", (port) => {
      resolve({ url: `ws://127.0.0.1:${port.trim()}`, stop });
    });
    void exited.then(() => {
      reject(new Error(`scripted_server.py stopped: ${errors.join("")}`));
    });
  });
}

export default async function setup(project: TestProject): Promise<(() => Promise<void>) | void> {
  const gatewayUrl = process.env.OPENROIS_GATEWAY_URL ?? "";
  project.provide("gatewayUrl", gatewayUrl);
  project.provide("engineId", process.env.OPENROIS_MOCK_ENGINE_ID ?? "mock");
  project.provide("scriptedUrl", "");
  if (gatewayUrl === "") {
    if (project.config.browser.enabled) {
      throw new Error("A browser run needs OPENROIS_GATEWAY_URL");
    }
    return;
  }
  const { url, stop } = await startScriptedServer();
  project.provide("scriptedUrl", url);
  return stop;
}
