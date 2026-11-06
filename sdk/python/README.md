# openrois-sdk

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

Python client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).

Connect to an OpenRoIS engine, discover the components of every connected physical robot, virtual avatar, or AI service, and drive them through the standard RoIS interfaces. Asyncio only.

> **Alpha, pre-1.0, unstable API.**

## Installation

### pip

```bash
pip install openrois-sdk
```

### From Source

```bash
git clone https://github.com/openrois/openrois.git
pip install -e ./openrois/sdk/python
```

## Usage

```python
import asyncio

from openrois.interfaces import RoISIdentifierType
from openrois.sdk import RoISClient, component_ref, component_type


async def main() -> None:
    async with RoISClient.connect("ws://localhost:8765") as client:
        # Find a component by type, and select it by ref in later calls.
        navigation = RoISIdentifierType(authority="OMG", code="Navigation")
        [nav] = await client.search(component_type(navigation))
        target = component_ref(nav)

        # Read state.
        status = await client.query("component_status", target)
        print(status)

        # React to events.
        client.on(
            "rois.event.notify_event",
            lambda event: print(event.event_type, event.results),
        )
        await client.subscribe("reached_target", target)

        # Record how each command ends, before running any.
        statuses: dict[str, str] = {}
        client.on(
            "rois.command.completed",
            lambda completed: statuses.update({completed.command_id: completed.status}),
        )

        # Reserve, configure, command, release.
        await client.bind(nav)
        await client.set_parameter(
            nav,
            [{"name": "target_positions", "data_type_ref": "string[]", "value": '["kitchen"]'}],
        )
        [command_id] = await client.execute([{"component_ref": nav, "command_type": "start"}])
        # ... later: statuses[command_id] is "OK" once the navigation has ended.
        await client.release(nav)


asyncio.run(main())
```

Run it against the Docker Compose stack at the repository root, which serves simulated components through a gateway.

## Waiting for a Command

RoIS has no operation that waits for a command, so neither does the client. `execute()` returns as soon as the engine accepts the commands. Each command ends later, with a `rois.command.completed` notification that names its id. `set_parameter()` works the same way.

A command that ends at once can complete before the reply reaches your code, so a listener added after `execute()` can miss it. The recipe has three steps:

1. Add the listener before the call, once for the whole session.
2. Record each status by `command_id`.
3. Read the status with the ids in the reply.

The quickstart above does this. To `await` a command, set an `asyncio.Event` from the same listener, and check the record first in case the command has already ended.

## API

`RoISClient` has one method per operation of the RoIS method catalog. Each takes the operation's IDL parameters in IDL order, validates them and the result against the catalog models in `openrois-interfaces`, and returns the result's out parameters as interface models. Inputs take a model or a mapping.

| RoIS interface | Methods |
|----------------|---------|
| System | `RoISClient.connect(url, *, request_timeout, connect_timeout)`, `disconnect()`, `get_profile(condition="")`, `get_error_detail(error_id, condition="")` |
| Command | `search(condition="")`, `bind(component_ref)`, `bind_any(condition="")`, `release(component_ref)`, `get_parameter(component_ref)`, `set_parameter(component_ref, parameters)`, `execute(command_unit_list)`, `get_command_result(command_id, condition="")` |
| Query | `query(query_type, condition="")` |
| Event | `subscribe(event_type, condition="")`, `unsubscribe(subscribe_id)`, `get_event_detail(event_id, condition="")` |

A streaming component is driven with these same methods. Carrying its media is planned.

- `get_profile()` returns an `EngineProfile` with `profile` and `component_profiles`: the engine profile and the profile of every component it lists, keyed by fully qualified ref.
- `execute()` takes a `command_unit_list`: commands that run in order, and `{"branch_list": [...], "delay_time": ...}` groups whose branches run at the same time, each branch in order. The commands need no `command_id`: the engine assigns one to each, and `execute()` returns them in order, branch by branch.
- `query()` and `subscribe()` go to the one component that declares the query or event type and matches the condition.

One client is one session. Bindings and subscriptions end with it, and there is no automatic reconnect, because a silent reconnect would hide that loss. After `close`, connect again and bind and subscribe again.

### Conditions

Every `condition` is a string in the OpenRoIS subset of CQL2-Text: `=` and `LIKE` comparisons, joined by `AND`, over `component_ref` and `component_type`. An empty string is no filter. The builders quote values for you:

| Builder | Writes |
|---------|--------|
| `component_ref("reachy_real/head")` | `component_ref = 'reachy_real/head'` |
| `component_type(RoISIdentifierType(authority="OMG", code="Navigation"))` | `component_type = 'urn:x-rois:def:component:OMG::Navigation'` |
| `like(COMPONENT_REF, "reachy_real/%")` | `component_ref LIKE 'reachy_real/%'` |
| `all_of(a, b)` | `a AND b` |

### Listening

`on(name, listener)` adds a listener and `off(name, listener)` removes it. Listeners of catalog notifications receive the validated params, as models from `openrois.interfaces`.

| Name | Listener receives |
|------|-------------------|
| `rois.event.notify_event` | `NotifyEventParams`, for every event of every subscription. Filter by `subscribe_id` or `event_type` |
| `rois.command.completed` | `CompletedParams`, when a command ends |
| `rois.system.notify_error` | `NotifyErrorParams`, when the engine reports an error |
| `rois.system.profile_changed` | `ProfileChangedParams`, when components join or leave |
| `close` | `(code, reason)` when the connection closes, from either side |
| `error` | An exception, for a message that cannot be used or a listener that raises |

A plain function runs inline in the task that reads the socket, in the order messages arrive, so it must not block. A coroutine function runs in a task of its own, so it can await a call on the client:

```python
async def on_person(event: NotifyEventParams) -> None:
    print(await client.get_event_detail(event.event_id))

client.on("rois.event.notify_event", on_person)
```

A listener that raises, in either form, never stops the client: the exception goes to the `error` listeners, and the other listeners still run. With no `error` listener, a fault goes to the `openrois.sdk.transport` logger at level `ERROR`. It is never raised.

### Closing

`async with` calls `disconnect()` when the block ends, and needs no `await` on `connect()`. Without it, call `disconnect()` yourself:

```python
client = await RoISClient.connect("ws://localhost:8765")
await client.search()
await client.disconnect()
```

## Error Handling

```python
from openrois.interfaces import ReturnCode
from openrois.sdk import RoISError

try:
    await client.bind("robot_1/navigation")
except RoISError as error:
    if error.return_code is ReturnCode.OUT_OF_RESOURCES:
        ...  # Another application holds the reservation.
```

| Error | Raised when | Carries |
|-------|-------------|---------|
| `RoISError` | A RoIS operation returns a code other than `OK` | `return_code`, `method` |
| `TransportError` | The base of the three below. Raised itself for a call on a closed client | |
| `RoISConnectionError` | The WebSocket cannot be opened, or closes while a request waits. Also a builtin `ConnectionError` | `url` |
| `RequestTimeoutError` | No response within the request timeout. Also a builtin `TimeoutError` | `method`, `request_id` |
| `RpcError` | The engine returns a JSON-RPC error: a protocol fault, such as an unknown method | `code`, `data` |
| `pydantic.ValidationError` | Params fail validation before they are sent, or a result does not match the catalog | |

## Timeouts

`RoISClient.connect()` takes the timeouts of the transport, in seconds:

```python
client = await RoISClient.connect(
    "ws://localhost:8765", request_timeout=5.0, connect_timeout=2.0
)
```

| Option | Default | Meaning |
|--------|---------|---------|
| `request_timeout` | 30.0 | How long a request waits for its response |
| `connect_timeout` | 10.0 | How long the WebSocket has to open |

A call can also be cancelled, with `asyncio.timeout` or `asyncio.wait_for`. The client keeps working, and it drops the reply when one arrives. A cancelled `connect()` ends at once and leaves the connection to close by itself.

## The Transport

`client.transport` is the `WebSocketTransport` under the client, for JSON-RPC methods outside the catalog. Nothing sent through it is validated.

```python
result = await client.transport.send("vendor.custom.method", {"level": 3})
```

Its `notification` event receives each notification as a mapping with `jsonrpc`, `method` and, when the message has them, `params`, in or outside the catalog.

It accepts messages of up to 16 MiB, where the default of the `websockets` package is 1 MiB, so that a large `get_profile` does not close the connection. A larger message closes the connection with code 1009, and the `close` listeners and the failed requests carry that code and its reason.

With `websockets` 15 or later, the client connects through the proxy that the environment names in variables such as `http_proxy` and `https_proxy`, for a local gateway too. Add the gateway to `no_proxy` to reach it directly. Earlier versions of `websockets` and the TypeScript client on its default socket ignore these variables.

## Modules

| Module | Contents |
|---|---|
| `openrois.sdk` | `RoISClient`, `EngineProfile`, the errors, and the condition builders |
| `openrois.sdk.transport` | `WebSocketTransport`, `TransportState` and `JsonRpcNotification` |
| `openrois.sdk.errors` | The errors |

## Tested Versions

The wire has no version handshake, so a mismatch shows only when a message carries a field the other side does not know. This release is tested against these versions together, which `testing/conformance/frozen.txt` pins:

| `openrois-sdk` | `openrois-gateway` | `openrois-engine` | `openrois-interfaces` | `openrois-components-core` |
|---|---|---|---|---|
| 0.1.0a1 | 0.1.0a1 | 0.1.0a2 | 0.1.0a6 | 0.1.0a1 |

## Development

```bash
pip install -e ../../interfaces/python -e ".[dev]"
pytest
mypy
ruff check src/ tests/
```

`tests/test_transport.py` runs the client against `testing/conformance/scripted_server.py`, which it starts by itself, so it needs no stack.

`tests/test_conformance.py` runs the conformance list of `testing/conformance/README.md`, one test per scenario. C01 to C17 need a live gateway with the mock adapter behind it, such as the Docker Compose stack at the repository root. They run when `OPENROIS_GATEWAY_URL` names the gateway, and are skipped otherwise. C18 to C21 and the coverage tests need no stack, so they always run.

```bash
docker compose up --build -d   # from the repository root
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 pytest
```

## License

Apache-2.0. See [LICENSE](./LICENSE).
