# Conformance

One list of scenarios for the contract between a gateway and its clients. Every client SDK
runs the same list against the same stack, a gateway with the
[mock adapter](../mock-adapter/README.md) behind it, with the id of the scenario in the name
of its test. A scenario missing from an SDK then shows up in a diff.

`wire_check.py` runs the list on raw JSON-RPC, with no SDK, to prove the engine and the
gateway on their own. The [TypeScript suite](#the-typescript-suite), the
[Python suite](#the-python-suite) and the [Unity suite](#the-unity-suite) run it through their
SDKs.

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

## The Scripted Server

`scripted_server.py` is a small WebSocket server with no engine, for C18 to C21. It needs only
the websockets package, and it serves every SDK and a browser from one process.

```bash
pip install websockets
python testing/conformance/scripted_server.py                # any free port on 127.0.0.1
python testing/conformance/scripted_server.py --host 0.0.0.0 --port 8770
```

It prints the port it binds on a line of its own, flushed at once, and runs until it is stopped.
A test runner starts it, reads that first line, and stops the process when the suite ends. The
runner then connects each test to `ws://127.0.0.1:<port>/<script>`, with the same client call as
for a gateway, because the path picks the script:

| Id | Path | What the server does | What the test does |
|----|------|----------------------|--------------------|
| C18 | `/reverse` | Holds requests until three have arrived, then answers the last one first | Calls `search` three times at once with different conditions |
| C19 | `/malformed` | Before it answers the first request, sends text that is not JSON, then a JSON object that is neither a reply nor a notification | Adds an `error` listener, calls `search`, and calls it again |
| C20 | `/drop` | Drops the connection with no close frame, 50 ms after the first request | Adds a `close` listener and calls `search`, once or more at once. Every call fails, and `close` fires with 1006 |
| C21 | `/close-1001` | Answers the first request, then closes with code 1001 and the reason `scripted close` | Adds a `close` listener and calls `search` |

Each script acts on a request, never on connect, so a test has time to add its listeners. On
every path, `rois.system.connect` and `rois.system.disconnect` answer OK, so a client runs its
usual session. `rois.command.search` answers OK with its condition as the only component ref,
so a caller can tell its reply from another. Every other method answers with `return_code` OK
alone, which does not satisfy every result in the catalog, so scenarios call `search`. A path
that names no script fails the handshake with 404.

`scripted_check.py` proves the server itself, with no SDK. It starts the server, reads the port,
and checks on raw messages what each script sends. It prints one line per script and exits
with 0 when every one passes.

```bash
pip install websockets
python testing/conformance/scripted_check.py
```

## The JavaScript SDK Suite

`sdk/javascript/tests/conformance.test.ts` has one test for each id from C01 to C21. W01 to
W03 stay with `wire_check.py`. The file uses only the public surface of the SDK and takes only
URLs, so one file runs in Node.js and in headless Chromium:

```bash
cd sdk/javascript
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npx vitest run tests/conformance.test.ts
npx playwright install --only-shell chromium      # once, for the browser run
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npm run test:browser
```

A global setup in Node.js starts the scripted server with `python3`, which needs the websockets
package, and hands the URLs to the test file. The suite waits until the mock adapter has joined,
so it can start with the stack. Without `OPENROIS_GATEWAY_URL`, Node.js skips the suite and a
browser run fails, because that run would prove nothing. `OPENROIS_MOCK_ENGINE_ID` names the
engine of the mock adapter, `mock` by default.

`tests/coverage.test.ts` needs no stack. It fails when an id of [the list](#the-list) has no
test, or a test has no id in the list, and when a method of the catalog has no client member.

## The Python Suite

`sdk/python/tests/test_conformance.py` has one test for each id from C01 to C21. W01 to W03
stay with `wire_check.py`. The file uses only the public surface of the SDK and takes only URLs:

```bash
pip install -e interfaces/python -e engine -e components/core \
  -e services/gateway -e "sdk/python[dev]"
openrois-gateway &
python testing/mock-adapter/mock_adapter.py --config testing/mock-adapter/adapter.fast.yaml &
cd sdk/python
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 pytest tests/test_conformance.py
```

A fixture starts the scripted server with the Python of the run, and stops it when the run ends.
The suite waits until the mock adapter has joined, so it can start with the stack. Without
`OPENROIS_GATEWAY_URL`, pytest skips C01 to C17 and still runs C18 to C21, because those need
only the scripted server. `OPENROIS_MOCK_ENGINE_ID` names the engine of the mock adapter, `mock`
by default.

The file ends with tests that need no stack. They fail when an id of [the list](#the-list) has
no test, or a test has no id in the list, and when a method of the catalog has no client member.

## The Unity Suite

`sdk/unity/Tests~/ConformanceTests.cs` has one test for each id from C01 to C21. W01 to W03
stay with `wire_check.py`. The file uses only the public surface of the SDK and takes only URLs.
It needs the .NET 10 SDK and no Unity, and the tilde keeps the folder out of the package as
Unity sees it:

```bash
pip install -e interfaces/python -e engine -e components/core \
  -e services/gateway websockets
openrois-gateway &
python testing/mock-adapter/mock_adapter.py --config testing/mock-adapter/adapter.fast.yaml &
cd sdk/unity/Tests~
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 dotnet test --filter "FullyQualifiedName~ConformanceTests"
```

The project compiles `sdk/unity/Runtime` as a Unity Editor does, with C# 9 on `netstandard2.1`,
and runs it against the assemblies in `Runtime/Plugins`, which take the place of the copies
inside .NET. So it tests what ships, and it does not prove a Unity player:
[the harness](../unity-harness/README.md) does that.

The first test that needs the scripted server starts it with `python3`, which needs the
websockets package, and the run stops it at the end. The suite waits until the mock adapter has
joined, so it can start with the stack. Without `OPENROIS_GATEWAY_URL`, `dotnet test` skips C01
to C17 and still runs C18 to C21, because those need only the scripted server.
`OPENROIS_MOCK_ENGINE_ID` names the engine of the mock adapter, `mock` by default.

C18 checks which caller got which reply, and not the order in which callers resumed, because
the thread pool decides that order. `scripted_check.py` proves that the server answers in reverse.

The file ends with tests that need no stack. They fail when an id of [the list](#the-list) has
no test, or a test has no id in the list, and when a method of the catalog has no client member,
or one whose last parameter is not an optional `CancellationToken`.

## Wire Fixtures

`capture.py` drives one session through the same stack and records the params and the result
of every catalog method, and every notification, into `interfaces/fixtures/wire.json`. Each
interface package parses every recorded body into its model and writes it back. Run it again
after a change to the models or to what an engine sends.

A plain session leaves much of the wire empty, so `WANTED` in the script names what the file
must also hold: fields that have to carry a value, such as the arguments of a command and the
results of `get_command_result`, and enumerators, such as the ways a command ends. The script
fails without writing the file when one is missing, as it does for a missing method.

```bash
pip install -e interfaces/python websockets
python testing/conformance/capture.py
```

## The Frozen Stack

Pull requests run the list against the tree. `frozen.txt` names the exact versions the client
SDKs are released against: each SDK release installs it into a venv of its own and runs its
suite there, so no SDK ships against a stack it was not tested with. A change a client can
see needs a new alpha and a change to that file.

```bash
python -m venv /tmp/frozen && . /tmp/frozen/bin/activate
pip install -r testing/conformance/frozen.txt websockets
openrois-gateway &
python testing/mock-adapter/mock_adapter.py --config testing/mock-adapter/adapter.fast.yaml &
```

Then run a suite as usual. The Python suite needs its SDK in the same venv, with
`pip install "./sdk/python[dev]"`, which leaves the pins as they are. The Unity suite needs nothing
more than that venv, because its `python3` has the websockets package. The mock adapter stays the
one of the tree, because it is a fixture and no package holds it.

## The List

`wire_check.py` covers C02 to C17, some of them through a raw request instead of a client
method. C18 to C21 test how a client handles a server, so they need the
[scripted server](#the-scripted-server). A client SDK suite covers C01 to C21.

| Id | Scenario |
|----|----------|
| C01 | `disconnect` is safe twice, in turn and overlapping, and a call after it fails locally with a transport error |
| C02 | `get_profile` lists the sub profile and each component profile |
| C03 | `search` with `component_ref`, `component_type`, `LIKE` and `AND` |
| C04 | A quote in a condition value survives the builders |
| C05 | `query` answers, and its condition picks one of several components that declare the query. UNSUPPORTED with no match, BAD_PARAMETER with several |
| C06 | `bind`, `bind_any`, `release`. A second client gets OUT_OF_RESOURCES on an actuator, and a sensor is shared |
| C07 | A bind ends with its session |
| C08 | `set_parameter` applies and completes. A bad value answers BAD_PARAMETER and the old value stays |
| C09 | `execute` from bind to `reached_target`, with ids from the reply |
| C10 | A sequence with branches returns ids in order, branch by branch |
| C11 | A listener added before `execute` or `set_parameter` sees every completion of the ids in the reply |
| C12 | A command ending badly aborts the later items. `release` aborts running commands with ABORT |
| C13 | `subscribe` twice returns one id, `subscribe` answers UNSUPPORTED when its condition selects a component without the event, `unsubscribe` of an unknown id answers OK, and events reach only their subscriber. Two clients subscribe to one event, and one leaving stops its events without stopping the other's |
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
every language and in a browser. C18 to C21 pick a script of the
[scripted server](#the-scripted-server) with the path of their URL. `mock/fault` is a component
of the mock adapter for the rest:

| Command | Effect |
|---------|--------|
| `raise_error` | The component raises ERROR and clears it after a second, which sends `rois.system.notify_error` |
| `peer_join` | A second engine joins the gateway and leaves it, which sends `rois.system.profile_changed` twice |
| `echo` | Takes the argument `text` and gives it back as a result, and declares a timeout in its profile |
| `end_with` | Ends with the status named by the argument `status`, for example `OUT_OF_RESOURCES` |

`mock/fault` also answers the query `echo`, and serves the event `echoed` that the command
`echo` emits. Both take the argument `text`, so its profile shows arguments on a query and on an
event.
