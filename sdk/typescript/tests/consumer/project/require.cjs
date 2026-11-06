const assert = require("node:assert/strict");
const { ConnectionError, RoISClient, componentRef } = require("@openrois/sdk");
const { ConnectionError: SameError, WebSocketTransport } = require("@openrois/sdk/transport");

assert.equal(componentRef("mock/navigation"), "component_ref = 'mock/navigation'");
assert.equal(typeof WebSocketTransport, "function");
assert.equal(ConnectionError, SameError);

assert.throws(() => require("@openrois/sdk/jsonrpc"), { code: "ERR_PACKAGE_PATH_NOT_EXPORTED" });

// Nothing listens on port 1, so this runs the default socket path up to its failure.
assert.rejects(RoISClient.connect("ws://127.0.0.1:1"), ConnectionError).then(() => {
  console.log("Node require passed.");
});
