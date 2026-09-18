# @openrois/sdk

TypeScript client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware
implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).

Connect to an OpenRoIS gateway, discover the components of every connected robot, avatar,
or service, and drive them through the standard RoIS interfaces. Runs in browsers and in
Node.js.

> **Alpha, pre-1.0, unstable API.** Not yet published to npm. Build from source as shown
> below.

## Install

```bash
# From a clone of the repository.
(cd interfaces/typescript && npm install && npm run build)
(cd sdk/typescript && npm install && npm run build)
```

```json title="package.json"
{
  "dependencies": {
    "@openrois/sdk": "file:../openrois/sdk/typescript"
  }
}
```

## Quickstart

```ts
import { RoISClient } from "@openrois/sdk";

const client = await RoISClient.connect("ws://localhost:8765");

// Discover what is connected, then pick a component by type.
const refs = await client.search();
const nav = refs.find((ref) => ref.includes("Navigation"))!;

// Read state.
const status = await client.query(nav, "component_status");

// React to events.
client.on("reached_target", (n) => console.log(n.params));
await client.subscribe(nav, "reached_target");

// Reserve, command, release.
await client.bind(nav);
await client.execute(nav, { command_type: "start" });
await client.release(nav);

await client.disconnect();
```

Run it against `examples/mock-engine` for a gateway with simulated components.

## API

| RoIS interface | Methods |
|----------------|---------|
| System | `RoISClient.connect()`, `disconnect()`, `getProfile()`, `getErrorDetail()` |
| Command | `search()`, `bind()`, `bindAny()`, `release()`, `getParameter()`, `setParameter()`, `execute()`, `getCommandResult()` |
| Query | `query()` |
| Event | `subscribe()`, `unsubscribe()`, `getEventDetail()` |
| Streaming | Planned |

| Event | Emitted for |
|-------|-------------|
| `<event_type>` | Each RoIS event under its own type, for example `reached_target` |
| `rois.event.notify` | Every RoIS event |
| `rois.command.completed` | Command completion |
| `rois.system.notify_error` | Engine errors |
| `notification` | Every JSON-RPC notification, including `rois.system.profile_changed` |
| `close` | The connection closed |

Some RoIS operations are not implemented by the engine yet. The
[wire protocol reference](https://openrois.org/docs/reference/wire-protocol) lists the
status of each one.

## Error Handling

```ts
import { RoISClient, RoISError } from "@openrois/sdk";

try {
  await client.bind("robot_1/Navigation");
} catch (err) {
  if (err instanceof RoISError && err.returnCode === "OUT_OF_RESOURCES") {
    // Another application holds the reservation.
  }
}
```

| Error | Raised when |
|-------|-------------|
| `RoISError` | A RoIS operation returns a code other than `OK` |
| `ConnectionError` | The WebSocket cannot be opened, or closes unexpectedly |
| `RequestTimeoutError` | No response within the request timeout (30 seconds by default) |
| `RpcError` | The gateway returns a JSON-RPC error object |

## Development

```bash
npm run build      # generate types and bundle with tsup
npm test           # vitest
npm run typecheck
npm run lint
```

## License

Apache-2.0. See [LICENSE](./LICENSE).
