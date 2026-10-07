# Mock Engine

A RoIS engine test double: a WebSocket server that speaks JSON-RPC 2.0 and answers every
method of the RoIS method catalog, so clients and SDKs can be developed and tested without
a robot.

It simulates three components of the engine `mock`, with profiles built from the
specification's XML component profiles:

| Ref | Profile | Function | Behavior |
|-----|---------|----------|----------|
| `mock/person_detection` | `OMG::PersonDetection` | sensing | Sends a `person_detected` event to every subscription every five seconds |
| `mock/navigation` | `OMG::Navigation` | actuation | `start` drives to the first of `target_positions`, reports `BUSY`, and ends with `reached_target` after three seconds |
| `mock/system_information` | `OMG::SystemInformation` | | Answers the `robot_position` and `engine_status` queries |

The person detection and navigation components also take the RoIS_Common commands
(`start`, `stop`, `suspend`, `resume`) and answer the `component_status` query.

## Behavior

The mock follows the method catalog the way an engine does:

- Every request is validated against the catalog before it is handled, and every result
  before it is sent. A method outside the catalog gets `METHOD_NOT_FOUND`, and params
  that fail the catalog model get `INVALID_PARAMS`.
- Conditions select components by `component_ref` and `component_type`, in the OpenRoIS
  subset of CQL2-Text.
- `query` and `subscribe` go to the one component that declares the query or event type
  and matches the condition.
- The navigation component takes commands and parameters from the client that bound it.
- The command table holds every `command_id`. Each command ends with a
  `rois.command.completed` notification, and `get_command_result` reads its results.
- `execute` runs its items in order, waits each item's `delay_time`, and runs the commands
  of a group at the same time.
- Events arrive as `rois.event.notify_event`, and `get_event_detail` reads each one for a
  minute after its notification.

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

`tests/engine.test.ts` drives the engine core directly. `tests/server.test.ts` starts the
WebSocket server on an ephemeral port, sends raw JSON-RPC messages, and runs client
sessions through `RoISClient` from [`@openrois/sdk`](../../sdk/typescript/README.md).

To embed the mock in other tests, import `createMockEngine` from `src/server.ts` and call
it with `{ port: 0, timing }`. The `timing` option sets how long commands, navigation,
detection intervals, and stored events last, in milliseconds.

## Scope

This is a test double, not a reference implementation. Its components are simulated and
drive nothing. For a real engine, use the Python `openrois-engine` package. See the
[architecture](https://openrois.org/docs/concepts/architecture).

## License

Apache-2.0.
