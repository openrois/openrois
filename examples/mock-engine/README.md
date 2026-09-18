# Mock Engine

A RoIS engine test double: a WebSocket server that speaks JSON-RPC 2.0 and answers with
canned components, so clients and SDKs can be developed and tested without a robot.

It registers three simulated components (`PersonDetection_0`, `Navigation_0`, and
`SystemInformation_0`) with realistic profiles, and implements the System, Command,
Query, and Event interfaces. Subscriptions to `person_detected` receive a canned
notification every five seconds.

## Run

```bash
# Once, from the repository root: build the types and the SDK this example depends on.
(cd interfaces/typescript && npm install && npm run build)
(cd sdk/typescript && npm install && npm run build)

npm install
npm start          # listens on ws://127.0.0.1:8765
```

Then point a client at `ws://localhost:8765`, for example
[`examples/hri-client`](../hri-client/README.md).

## Test

```bash
npm test           # vitest
```

The tests import `createMockEngine` directly and bind an ephemeral port, so they need no
running server.

## Scope

This is a test double, not a reference implementation. It answers with fixed data and
does not drive anything. For a real engine, use the Python `openrois-core` package. See
the [architecture](https://openrois.org/docs/concepts/architecture).

## License

Apache-2.0.
