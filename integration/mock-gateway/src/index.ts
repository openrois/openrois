/**
 * Standalone entry point: start the mock gateway on the default port.
 *
 * Run with `npm start`. Intended for manual testing with a WebSocket client.
 * Automated tests import {@link createMockGateway} directly and bind an
 * ephemeral port instead.
 */

import { createMockGateway } from "./server";

const gateway = await createMockGateway();
console.log(`Mock RoIS gateway listening on ws://127.0.0.1:${gateway.port}`);
