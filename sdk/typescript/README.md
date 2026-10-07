# @openrois/sdk

TypeScript client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware
implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).

Connect to an OpenRoIS engine, discover the components of every connected robot, avatar,
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
import { RoISClient, componentRef, componentType } from "@openrois/sdk";

const client = await RoISClient.connect("ws://localhost:8765");

// Find a component by type, and select it by ref in later calls.
const [nav] = await client.search(componentType({ authority: "OMG", code: "Navigation" }));
const target = componentRef(nav);

// Read state.
const status = await client.query("component_status", target);

// React to events.
client.on("reached_target", (event) => console.log(event.results));
await client.subscribe("reached_target", target);

// Reserve, configure, command, release.
await client.bind(nav);
await client.setParameter(nav, [
  { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' },
]);
const [commandId] = await client.execute([{ component_ref: nav, command_type: "start" }]);
client.on("rois.command.completed", ({ command_id, status }) => {
  if (command_id === commandId) console.log("navigation ended:", status);
});
await client.release(nav);

await client.disconnect();
```

Run it against `examples/mock-engine` for an engine with simulated components.

## API

`RoISClient` has one method per operation of the RoIS method catalog. Each takes the
operation's IDL parameters in IDL order, validates them and the result against the
catalog schemas in `@openrois/interfaces`, and returns the result's out parameters.

| RoIS interface | Methods |
|----------------|---------|
| System | `RoISClient.connect(url)`, `disconnect()`, `getProfile(condition?)`, `getErrorDetail(errorId, condition?)` |
| Command | `search(condition?)`, `bind(ref)`, `bindAny(condition?)`, `release(ref)`, `getParameter(ref)`, `setParameter(ref, parameters)`, `execute(commandUnitList)`, `getCommandResult(commandId, condition?)` |
| Query | `query(queryType, condition?)` |
| Event | `subscribe(eventType, condition?)`, `unsubscribe(subscribeId)`, `getEventDetail(eventId, condition?)` |
| Streaming | Planned |

- `getProfile()` returns `{ profile, component_profiles }`: the engine profile and the
  profile of every component it lists, keyed by fully qualified ref.
- `execute()` takes a `command_unit_list`: commands that run in order, and
  `{ command_list, delay_time }` groups whose commands run at the same time. A command
  without a `command_id` gets a UUID. `execute()` returns every `command_id` in order, and
  each command ends with a `rois.command.completed` notification.
- `query()` and `subscribe()` go to the one component that declares the query or event
  type and matches the condition.

`examples/mock-engine` implements this method catalog. The Python engine is moving to it
(in progress).

### Conditions

Every `condition` is a string in the OpenRoIS subset of CQL2-Text: `=` and `LIKE`
comparisons, joined by `AND`, over `component_ref` and `component_type`. An empty string
is no filter. The builders quote values for you:

| Builder | Writes |
|---------|--------|
| `componentRef("reachy_real/head")` | `component_ref = 'reachy_real/head'` |
| `componentType({ authority: "OMG", code: "Navigation" })` | `component_type = 'urn:x-rois:def:component:OMG::Navigation'` |
| `like(COMPONENT_REF, "reachy_real/%")` | `component_ref LIKE 'reachy_real/%'` |
| `allOf(a, b)` | `a AND b` |

### Events

Listeners of catalog notifications receive the validated params, typed from
`RoISNotificationMap`.

| Event | Listener receives |
|-------|-------------------|
| `rois.event.notify_event` | `NotifyEventParams`, for every event of a subscription |
| `<event_type>` | The same `NotifyEventParams`, under the event's type, for example `reached_target` |
| `rois.command.completed` | `CompletedParams`, when a command ends |
| `rois.system.notify_error` | `NotifyErrorParams`, when the engine reports an error |
| `rois.system.profile_changed` | `ProfileChangedParams`, when components join or leave |
| `notification` | The JSON-RPC envelope of every notification |
| `close` | `(code, reason)` when the connection closes |
| `error` | Transport faults, and notifications whose params fail validation |

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

| Error | Raised when |
|-------|-------------|
| `RoISError` | A RoIS operation returns a code other than `OK` |
| `ConnectionError` | The WebSocket cannot be opened, or closes unexpectedly |
| `RequestTimeoutError` | No response within the request timeout (30 seconds by default) |
| `RpcError` | The engine returns a JSON-RPC error: a protocol fault, such as an unknown method |
| `ZodError` | Params fail validation before they are sent, or a result does not match the catalog |

## Development

```bash
npm run build      # generate types and bundle with tsup
npm test           # vitest
npm run typecheck
npm run lint
```

`tests/gateway.test.ts` runs full client sessions against a live gateway with the mock
adapter behind it, such as the Docker Compose stack at the repository root. It runs when
`OPENROIS_GATEWAY_URL` names the gateway, and is skipped otherwise:

```bash
docker compose up --build -d   # from the repository root
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npm test
```

## License

Apache-2.0. See [LICENSE](./LICENSE).
