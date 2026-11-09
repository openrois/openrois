# Unity Harness

A minimal Unity project that proves the bundled interface types and `RoISClient` in real players,
where `dotnet test` cannot reach: IL2CPP, managed code stripping, the Unity class libraries, and the
main thread. It also proves in the Editor that a client does not outlive Play Mode. It is run by
hand before a tag, because automating it needs a Unity license in CI.

## What It Checks

| Check | Lines | What it does |
|-------|-------|--------------|
| Wire | `wire`, `wire coverage` | Parses each entry of `interfaces/fixtures/wire.json` into its generated type with `RoISJson.Options`, writes it back, compares it to the body, and parses and writes it again. Every catalog message must have an entry |
| Refusals | `refuse-missing`, `refuse-unknown` | Takes each required field away, and adds an unknown field, in every object of every entry at any depth. Only a `JsonException` counts as a refusal, so an exception from stripping is a failure |
| Vectors | `condition`, `value`, `edge`, `double` | Runs `conditions.json`, `values.json` and `value-edges.json` except its `conditions` list, with the cases that file records as a C# difference left out. Only a `FormatException` counts as a refused value, and only a `JsonException` as a refused model |
| Session | `session` | Runs connect, search, get_profile, bind, execute, the completed notification and disconnect on `ClientWebSocket` against a live gateway. Every message goes through the generated types |
| Main thread | `main-thread` | Checks the thread after every await in the player and first thing in every callback of the conformance list, one line each. Two controls prove the check can fail: a worker thread reports another id, and a client connected from a worker runs its listener away from the main thread |
| Conformance | `conformance` | Runs C01 to C21 of [the list](../conformance/README.md) through `RoISClient`, not through raw JSON: C01 to C17 against the live gateway, C18 to C21 against `testing/conformance/scripted_server.py`. `conformance coverage` compares the scenarios to the list, which ships in the player. A fault no scenario expects fails the run |

The player prints one line per check, each starting with `HARNESS`, then a last line:

```
HARNESS PASS wire params rois.command.execute
HARNESS PASS session completed gateway/cmd-1
HARNESS RESULT OK passed=<count> failed=0
```

The exit code is 0 only when every check passed. The count moves between runs, because each search
for the adapter, each event of the mock adapter and each wait for one is a check. A session or a
scenario that hangs fails after 60 seconds, and any other hang after 300 seconds.

The scenarios follow `sdk/unity/Tests~/ConformanceTests.cs` with one difference: C18 checks who got
which reply and not the order the callers resumed in, as that suite does.

## Run

Unity writes `.meta` files and a `Library` folder into a `file:` package, so **never open this
project in place**. `run.sh` copies this folder, `sdk/unity` and `interfaces/fixtures` to a new
folder, keeping their relative paths, and builds there. It refuses a folder that exists. No
`ProjectSettings` folder is kept here, so one project opens on every Editor version without an
upgrade: `run.sh` writes the version file into the copy, and the build script sets the player.

Desktop runs need a virtual environment that holds the gateway and the mock adapter:

```bash
python3.12 -m venv /path/to/venv
/path/to/venv/bin/pip install -e interfaces/python -e components/core \
  -e engine -e services/gateway
export OPENROIS_VENV=/path/to/venv
```

Then, one Editor at a time, from the repository root:

```bash
# Linux IL2CPP with stripping High. Each takes a few minutes.
testing/unity-harness/run.sh /path/to/new-folder-1 6000.0.85f2 linux-il2cpp
testing/unity-harness/run.sh /path/to/new-folder-2 6000.3.28f1 linux-il2cpp
testing/unity-harness/run.sh /path/to/new-folder-3 6000.6.5f1 linux-il2cpp

# Linux Mono, with stripping off as Unity sets it by default for Mono.
testing/unity-harness/run.sh /path/to/new-folder-4 6000.0.85f2 linux-mono
```

`run.sh` starts a gateway on a free port with the mock adapter behind it, and the scripted server,
runs the player with `-batchmode -nographics`, prints the `HARNESS` lines, stops the three
processes, and exits with the exit code of the player. The work folder keeps `build.log`,
`player.log`, `gateway.log`, `adapter.log` and `scripted.log`. Editors are looked up in
`~/Unity/Hub/Editor`, or in `UNITY_EDITORS`.

`OPENROIS_HARNESS_STRIPPING` overrides the level, with a name of `ManagedStrippingLevel` such as
`Medium`. Mono stays below High because at High every read through `System.Text.Json` fails on Mono
with a `FieldAccessException`. IL2CPP passes at High.

## Play Mode

`dotnet test` has no Editor, so this runs in one, in batch mode with `-nographics` and with domain
reload off, which is what leaves a forgotten socket alive:

```bash
testing/unity-harness/run.sh /path/to/new-folder-7 6000.6.5f1 editor-playmode
```

No player is built. Each of two Play Mode cycles opens a client bound to `mock/navigation` on the
live gateway, one on a peer that records it, one on a peer that stops answering, a client that
reconnects from its `close` listener as the README of the package teaches, and an attempt to connect
that is never answered, then leaves Play Mode without ending any of them. Then it checks:

| Check | What it shows |
|-------|---------------|
| `session closed`, `record closed` | `close` fires once with 1000, in a context captured in Play Mode, on the main thread |
| `peer saw one disconnect`, `peer saw a normal close` | The peer got one `rois.system.disconnect` and a close frame, so the client did end |
| `deaf peer dropped`, `deaf peer lost the socket` | A peer that stopped answering loses its connection, and leaving takes about a second |
| `attempt failed`, `attempt lost the socket` | The attempt in flight fails and leaves no socket behind |
| `recipe left no client`, `recipe tried to connect during the exit` | The close of leaving Play Mode reaches the script before `OnDestroy`, and its connect is refused. The peer saw one connection, and it closed |
| `the engine released the bind` | A new client binds the same actuator, which the engine allows only if the first one left |
| `reload disconnect`, `reload close` | The same for an assembly reload, on a client opened outside Play Mode |

`lifecycle_server.py` is the peer. It writes what it saw to `lifecycle.record` in the work folder,
next to `playmode.log`. Domain reload on is not covered here, because the driver lives in memory
that a reload would clear. The run ends with the same `HARNESS RESULT` line as a player.

## Android

The addresses are set at build time, in `harness.json` in StreamingAssets, because a launched app
has no environment and a device reaches its servers over the LAN. Use the address of this machine
on that network:

```bash
export OPENROIS_GATEWAY_URL=ws://192.168.1.20:8765 OPENROIS_SCRIPTED_URL=ws://192.168.1.20:8766
testing/unity-harness/run.sh /path/to/new-folder-5 6000.0.85f2 android
testing/unity-harness/run.sh /path/to/new-folder-6 6000.6.5f1 android
```

This builds an ARM64 IL2CPP APK with stripping High at `player/harness.apk` and stops there. To run
it, start a gateway and the scripted server where the LAN can reach them, then install and launch
the APK. Neither authenticates its peers, so bind another interface only on a network you trust.

```bash
"$OPENROIS_VENV/bin/openrois-gateway" --host 0.0.0.0 --port 8765 &
"$OPENROIS_VENV/bin/python" testing/mock-adapter/mock_adapter.py \
  --config testing/mock-adapter/adapter.fast.yaml --gateway-url ws://127.0.0.1:8765 &
"$OPENROIS_VENV/bin/python" testing/conformance/scripted_server.py --host 0.0.0.0 --port 8766 &

adb devices
adb install -r /path/to/new-folder-5/player/harness.apk
adb logcat -c
adb shell monkey -p org.openrois.harness -c android.intent.category.LAUNCHER 1
adb logcat -s Unity | grep --line-buffered HARNESS
```

Android gives no exit code to a caller, so read the `HARNESS RESULT` line.

## Files

| Path | What it is |
|------|------------|
| `Assets/HarnessRunner.cs` | The fixture and session checks. It starts itself after the scene loads, so the scene stays empty |
| `Assets/HarnessConformance.cs` | The conformance list through `RoISClient` |
| `Assets/Editor/HarnessBuild.cs` | The batch mode build: copies the fixtures and the list to StreamingAssets, makes the scene, sets the player |
| `Assets/Editor/HarnessPlayMode.cs` | The Play Mode run |
| `lifecycle_server.py` | The peer of the Play Mode run, which records what a client did |
| `Packages/manifest.json` | The SDK as `file:../../../sdk/unity` |
| `run.sh` | Copies, builds, starts the servers and runs the player or the Editor |

The harness declares no class of its own for `System.Text.Json`, and it keeps no `link.xml` of its
own. High stripping removes the members of a class that only reflection reaches, so such a class
would need `[Preserve]`. Any `link.xml` here could also hide a gap in the one the SDK ships, which
is the one a user's player depends on.
