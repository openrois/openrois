import assert from "node:assert/strict";
import { ConnectionError, RoISClient, componentRef } from "@openrois/sdk";
import { ConnectionError as SameError, WebSocketTransport } from "@openrois/sdk/transport";

assert.equal(componentRef("mock/navigation"), "component_ref = 'mock/navigation'");
assert.equal(typeof WebSocketTransport, "function");
assert.equal(ConnectionError, SameError);

// Nothing listens on port 1, so this runs the default socket path up to its failure.
await assert.rejects(RoISClient.connect("ws://127.0.0.1:1"), ConnectionError);

await assert.rejects(import("@openrois/sdk/jsonrpc"), { code: "ERR_PACKAGE_PATH_NOT_EXPORTED" });

console.log("Node ESM passed.");
