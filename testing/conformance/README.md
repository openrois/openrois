# Conformance

One list of scenarios for the contract between a gateway and its clients. Every client SDK
runs the same list against the same stack, a gateway with the
[mock adapter](../mock-adapter/README.md) behind it, with the id of the scenario in the name
of its test. A scenario missing from an SDK then shows up in a diff.

`wire_check.py` runs the list on raw JSON-RPC, with no SDK, to prove the engine and the
gateway on their own. The client SDK suites and the scripted server are in progress.

## Run

```bash
docker compose up --build -d                      # from the repository root
pip install websockets
python testing/conformance/wire_check.py
```

It prints one line per scenario and exits with 0 when every one passes.
`OPENROIS_ADAPTER_CONFIG=/opt/mock-adapter/adapter.fast.yaml` on `docker compose up` makes
the simulated work ten times faster.

`wire_check.py --watch-close` holds one connection and exits with 0 when the gateway closes
it with code 1001. CI runs it across `docker compose stop` to check a graceful stop.

## The Frozen Stack

Pull requests run the list against the tree. `frozen.txt` names the exact versions the client
SDKs are released against: each SDK release installs it into a venv of its own and runs its
suite there, so no SDK ships against a stack it was not tested with. A change a client can
see needs a new alpha and a change to that file.

## The List

`wire_check.py` covers C02 to C17, some of them through a raw request instead of a client
method. C18 to C21 test how a client handles a server, so they need the scripted server.

| Id | Scenario |
|----|----------|
| C01 | `disconnect` is safe twice, and a call after it fails locally with a transport error |
| C02 | `get_profile` lists the sub profile and each component profile |
| C03 | `search` with `component_ref`, `component_type`, `LIKE` and `AND` |
| C04 | A quote in a condition value survives the builders |
| C05 | `query` answers. UNSUPPORTED with no match, BAD_PARAMETER with several |
| C06 | `bind`, `bind_any`, `release`. A second client gets OUT_OF_RESOURCES on an actuator, and a sensor is shared |
| C07 | A bind ends with its session |
| C08 | `set_parameter` applies and completes. A bad value answers BAD_PARAMETER and the old value stays |
| C09 | `execute` from bind to `reached_target`, with ids from the reply |
| C10 | A sequence with branches returns ids in order, branch by branch |
| C11 | A listener added before `execute` or `set_parameter` sees every completion of the ids in the reply |
| C12 | A command ending badly aborts the later items. `release` aborts running commands with ABORT |
| C13 | `subscribe` twice returns one id, `unsubscribe` of an unknown id answers OK, and events reach only their subscriber. Two clients subscribe to one event, and one leaving does not stop the other |
| C14 | `notify_event` results equal `get_event_detail` |
| C15 | `notify_error` reaches each client that holds the component, and `get_error_detail` reads it |
| C16 | `profile_changed` arrives when an engine joins and when it leaves |
| C17 | METHOD_NOT_FOUND through the raw `send` reaches the caller as `RpcError` |
| C18 | Replies that arrive in reverse order reach the right callers |
| C19 | A malformed message reaches the `error` listener, or the log, and the client keeps working |
| C20 | A dropped connection fails pending requests and fires `close` |
| C21 | A server close reaches `close` with its code and reason |

These cover what a client SDK cannot reach:

| Id | Scenario |
|----|----------|
| W01 | Requests before `connect` and after `disconnect` answer ERROR |
| W02 | Requests in parallel are answered by id |
| W03 | A message over 1 MiB closes the connection with 1009 |

The stack keeps two behaviors that the list treats as they are: `release` answers OK without
a bind, and stopping the gateway closes its sessions without a notification.

## How Scenarios Trigger Faults

Everything a scenario needs is reachable from a URL or a RoIS call, so the list works in
every language and in a browser. `mock/fault` is a component of the mock adapter for this:

| Command | Effect |
|---------|--------|
| `raise_error` | The component raises ERROR and clears it after a second, which sends `rois.system.notify_error` |
| `peer_join` | A second engine joins the gateway and leaves it, which sends `rois.system.profile_changed` twice |
