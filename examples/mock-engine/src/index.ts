/**
 * Standalone entry point: start the mock engine on the default port.
 *
 * Run with `npm start`. Intended for manual testing with a WebSocket client.
 * Automated tests import {@link createMockEngine} directly and bind an
 * ephemeral port instead.
 */

import { createMockEngine } from "./server";

const engine = await createMockEngine();
console.log(`Mock RoIS engine listening on ws://127.0.0.1:${engine.port}`);
