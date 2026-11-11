# @openrois/sdk

![Node.js](https://img.shields.io/badge/Node.js-22.12+-5FA04E?logo=nodedotjs&logoColor=white)

JavaScript client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).

Connect to an OpenRoIS engine, discover the components of every connected physical robot, virtual avatar, or digital service, and drive them through the standard RoIS interfaces. Runs in browsers and in Node.js.

> **Alpha, pre-1.0, unstable API.**

## Installation

### npm

```bash
npm install @openrois/sdk
```

### From Source

```bash
git clone https://github.com/openrois/openrois.git
cd openrois/sdk/javascript
npm install
npm run build
```

Then reference from your project:

```json
{
  "dependencies": {
    "@openrois/sdk": "file:../path/to/openrois/sdk/javascript"
  }
}
```

## Usage

```ts
import { RoISClient, componentRef, componentType } from "@openrois/sdk";

const client = await RoISClient.connect("ws://localhost:8765");

// Find a component by type, and select it by ref in later calls.
const [nav] = await client.search(componentType({ authority: "OMG", code: "Navigation" }));
const target = componentRef(nav);

// Read state.
const status = await client.query("component_status", target);

// React to events.
client.on("rois.event.notify_event", ({ event_type, results }) => {
  console.log(event_type, results);
});
await client.subscribe("reached_target", target);

// Record how each command ends, before running any.
const statuses = new Map<string, string>();
const waiters = new Map<string, () => void>();
client.on("rois.command.completed", ({ command_id, status }) => {
  statuses.set(command_id, status);
  waiters.get(command_id)?.();
});

// Reserve, configure, command, wait, release.
await client.bind(nav);
await client.setParameter(nav, [
  { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' },
]);
const [commandId] = await client.execute([{ component_ref: nav, command_type: "start" }]);
// Wait here, because release aborts a running command, which then ends with ABORT.
if (!statuses.has(commandId)) {
  await new Promise<void>((resolve) => waiters.set(commandId, resolve));
}
console.log(statuses.get(commandId));
await client.release(nav);

await client.disconnect();
```

Run it against the Docker Compose stack at the repository root, which serves simulated components through a gateway.

## Waiting for a Command

RoIS has no operation that waits for a command, so neither does the client. `execute()` returns as soon as the engine accepts the commands. Each command ends later, with a `rois.command.completed` notification that names its id. `setParameter()` works the same way.

A command that ends at once can complete before the reply reaches your code, so a listener added after `execute()` can miss it. The recipe has three steps:

1. Add the listener before the call, once for the whole session.
2. Record each status by `command_id`.
3. Read the status with the ids in the reply.

The quickstart above does this, and checks the record first, because a command that has already ended fires no listener. A real application also stops waiting on `close`, or after a timeout.

Wait before you release the component: `release()` aborts your running commands on it, and they end with `ABORT`. `disconnect()` aborts them too.

## API

`RoISClient` has one method per operation of the RoIS method catalog. Each takes the operation's IDL parameters in IDL order, validates them and the result against the catalog schemas in `@openrois/interfaces`, and returns the result's out parameters.

| RoIS interface | Methods |
|----------------|---------|
| System | `RoISClient.connect(url, options?)`, `disconnect()`, `getProfile(condition?)`, `getErrorDetail(errorId, condition?)` |
| Command | `search(condition?)`, `bind(ref)`, `bindAny(condition?)`, `release(ref)`, `getParameter(ref)`, `setParameter(ref, parameters)`, `execute(commandUnitList)`, `getCommandResult(commandId, condition?)` |
| Query | `query(queryType, condition?)` |
| Event | `subscribe(eventType, condition?)`, `unsubscribe(subscribeId)`, `getEventDetail(eventId, condition?)` |

A streaming component is driven with these same methods. Carrying its media is planned.

- `getProfile()` returns `{ profile, component_profiles }`: the engine profile and the profile of every component it lists, keyed by fully qualified ref.
- `execute()` takes a `command_unit_list`: commands that run in order, and `{ branch_list, delay_time }` groups whose branches run at the same time, each branch in order. The commands carry no `command_id`: the engine assigns one to each, and `execute()` returns them in order, branch by branch.
- `query()` and `subscribe()` go to the one component that declares the query or event type and matches the condition.

One client is one session. Bindings and subscriptions end with it, and there is no automatic reconnect, because a silent reconnect would hide that loss. After `close`, connect again and bind and subscribe again.

### Conditions

Every `condition` is a string in the OpenRoIS subset of CQL2-Text: `=` and `LIKE` comparisons, joined by `AND`, over `component_ref` and `component_type`. An empty string is no filter. The builders quote values for you:

| Builder | Writes |
|---------|--------|
| `componentRef("reachy_real/head")` | `component_ref = 'reachy_real/head'` |
| `componentType({ authority: "OMG", code: "Navigation" })` | `component_type = 'urn:x-rois:def:component:OMG::Navigation'` |
| `like(COMPONENT_REF, "reachy_real/%")` | `component_ref LIKE 'reachy_real/%'` |
| `allOf(a, b)` | `a AND b` |

### Listening

`on(name, listener)` adds a listener and `off(name, listener)` removes it. Listeners of catalog notifications receive the validated params, typed from `RoISNotificationMap`.

| Name | Listener receives |
|------|-------------------|
| `rois.event.notify_event` | `NotifyEventParams`, for every event of every subscription. Filter by `subscribe_id` or `event_type` |
| `rois.command.completed` | `CompletedParams`, when a command ends |
| `rois.system.notify_error` | `NotifyErrorParams`, when the engine reports an error |
| `rois.system.profile_changed` | `ProfileChangedParams`, when components join or leave |
| `close` | `(code, reason)` when the connection closes, from either side |
| `error` | An `Error`, for a message that cannot be used or a listener that throws |

A listener that throws, and an `async` listener that rejects, never stop the client: the error goes to the `error` listeners, and the other listeners still run. With no `error` listener, a fault is written to `console.error`. It is never thrown.

### Closing

`await using` calls `disconnect()` when the block ends:

```ts
{
  await using client = await RoISClient.connect("ws://localhost:8765");
  await client.search();
}
```

The syntax runs natively in Node.js 24. For Node.js 22, compile it with TypeScript.

## Error Handling

```ts
import { RoISClient, RoISError } from "@openrois/sdk";

try {
  await client.bind("robot_1/navigation");
} catch (err) {
  if (err instanceof RoISError && err.returnCode === "OUT_OF_RESOURCES") {
    // Another application holds the reservation.
  }
}
```

| Error | Raised when | Carries |
|-------|-------------|---------|
| `RoISError` | A RoIS operation returns a code other than `OK` | `returnCode`, `method` |
| `TransportError` | The base of the three below. Raised itself for a call on a closed client | |
| `ConnectionError` | The WebSocket cannot be opened, or closes while a request waits | `url` |
| `RequestTimeoutError` | No response within the request timeout | `method`, `requestId` |
| `RpcError` | The engine returns a JSON-RPC error: a protocol fault, such as an unknown method | `code`, `data` |
| `ZodError` | Params fail validation before they are sent, or a result does not match the catalog | |

## Node.js and Browsers

The package is one ES module build, with no separate CommonJS build. `import` works in Node.js 22.12 or later and in browsers, and `require` works from Node.js 22.12. `moduleResolution` can be `nodenext` or `bundler`. It uses the global `WebSocket`, which both have, so it installs no WebSocket package.

Browsers are the target, but this release has run in headless Chromium only. Firefox and Safari have not been run. `wss://` has not been exercised: every run used `ws://`. The gateway does not authenticate connections in the alpha releases, so use it on trusted networks only.

`RoISClient.connect()` takes the transport options, with times in milliseconds:

```ts
const client = await RoISClient.connect("ws://localhost:8765", {
  transport: { requestTimeout: 5_000, connectTimeout: 2_000 },
});
```

| Option | Default | Meaning |
|--------|---------|---------|
| `requestTimeout` | 30000 | How long a request waits for its response |
| `connectTimeout` | 10000 | How long the WebSocket has to open |
| `webSocketFactory` | The global `WebSocket` | Creates the socket for a URL |

`webSocketFactory` is for a socket the global `WebSocket` cannot open, for example one with headers through the `ws` package:

```ts
import WebSocket from "ws";
import type { WebSocketLike } from "@openrois/sdk/transport";

const client = await RoISClient.connect("wss://engine.example.com", {
  transport: {
    webSocketFactory: (url) =>
      new WebSocket(url, { headers: { "x-site": "lab-1" } }) as unknown as WebSocketLike,
  },
});
```

## The Transport

`client.transport` is the `WebSocketTransport` under the client, for JSON-RPC methods outside the catalog. Nothing sent through it is validated.

```ts
const result = await client.transport.send("vendor.custom.method", { level: 3 });
```

## Subpath Exports

| Import path | Contents |
|---|---|
| `@openrois/sdk` | `RoISClient`, its types, the errors, and the condition builders |
| `@openrois/sdk/transport` | `WebSocketTransport`, `WebSocketLike`, `TransportOptions`, `TransportEvents`, `TransportState`, and the transport errors |

## Tested Versions

The wire has no version handshake, so a mismatch shows only when a message carries a field the other side does not know. This release is tested against these versions together, which `testing/conformance/frozen.txt` pins:

| `@openrois/sdk` | `@openrois/interfaces` | `openrois-gateway` | `openrois-engine` | `openrois-interfaces` | `openrois-components-core` |
|---|---|---|---|---|---|
| 0.1.0 | 0.1.0 | 0.1.0 | 0.1.0 | 0.1.0 | 0.1.0 |
| 0.1.0-alpha.1 | 0.1.0-alpha.6 | 0.1.0a1 | 0.1.0a2 | 0.1.0a6 | 0.1.0a1 |

## Development

```bash
npm run build          # bundle with tsup
npm test               # vitest
npm run test:browser   # the conformance list in headless Chromium, needs the stack below
npm run test:consumer  # build, pack, and check the tarball from a clean project
npm run typecheck
npm run lint
```

The SDK depends on `@openrois/interfaces` from npm. To test it against the interfaces in the tree, build them and install them over that copy:

```bash
npm install ../../interfaces/typescript --no-save
```

`tests/conformance.test.ts` runs the conformance list of `testing/conformance/README.md`, and `tests/gateway.test.ts` runs full client sessions. Both need a live gateway with the mock adapter behind it, such as the Docker Compose stack at the repository root. They run when `OPENROIS_GATEWAY_URL` names the gateway, and are skipped otherwise.

With that variable set, every run starts `testing/conformance/scripted_server.py` with `python3`, which needs the `websockets` package. Without it the whole run fails, not only these two files.

```bash
docker compose up --build -d   # from the repository root
pip install websockets
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npm test
npx playwright install --only-shell chromium   # once, for the browser run
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npm run test:browser
```

With `OPENROIS_SDK_PACKAGE` naming an unpacked tarball inside this folder, these tests import its `dist` in place of `src`, which is how the release workflow runs them.

## License

Apache-2.0. See [LICENSE](./LICENSE).
