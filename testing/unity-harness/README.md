# Unity Harness

A minimal Unity project that proves the bundled interface types and `ClientWebSocket` in real
players, where `dotnet test` cannot reach: IL2CPP, managed code stripping, the Unity class
libraries, and the main thread. It is run by hand before a tag, because automating it needs a
Unity license in CI.

## What It Checks

| Check | Lines | What it does |
|-------|-------|--------------|
| Wire | `wire`, `wire coverage` | Parses each entry of `interfaces/fixtures/wire.json` into its generated type with `RoISJson.Options`, writes it back, compares it to the body, and parses and writes it again. Every catalog message must have an entry |
| Refusals | `refuse-missing`, `refuse-unknown` | Takes each required field away, and adds an unknown field, in every object of every entry at any depth. Only a `JsonException` counts as a refusal, so an exception from stripping is a failure |
| Vectors | `condition`, `value`, `edge`, `double` | Runs `conditions.json`, `values.json` and `value-edges.json` except its `conditions` list, with the cases that file records as a C# difference left out. Only a `FormatException` counts as a refused value, and only a `JsonException` as a refused model |
| Session | `session` | Runs connect, search, get_profile, bind, execute, the completed notification and disconnect on `ClientWebSocket` against a live gateway. Every message goes through the generated types |
| Main thread | `main-thread` | Checks the thread after every await in the player, one line each. A control proves that a worker thread reports another id |

The player prints one line per check, each starting with `HARNESS`, then a last line:

```
HARNESS PASS wire params rois.command.execute
HARNESS PASS session completed gateway/cmd-1
HARNESS RESULT OK passed=<count> failed=0
```

The exit code is 0 only when every check passed. The count moves a little between runs, because
each search for the adapter is a check and the adapter takes a moment to join. A session that hangs
fails after 60 seconds, and any other hang after 180 seconds.

## Run

Unity writes `.meta` files and a `Library` folder into a `file:` package, so **never open this
project in place**. `run.sh` copies this folder, `sdk/unity` and `interfaces/fixtures` to a new
folder, keeping their relative paths, and builds there. It refuses a folder that exists. No
`ProjectSettings` folder is kept here, so one project opens on every Editor version without an
upgrade: `run.sh` writes the version file into the copy, and the build script sets the player.

Desktop runs need a virtual environment that holds the gateway and the mock adapter:

```bash
python3.12 -m venv /path/to/venv
/path/to/venv/bin/pip install -e interfaces/python -e components/core -e components/common \
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

`run.sh` starts a gateway on a free port with the mock adapter behind it, runs the player with
`-batchmode -nographics`, prints the `HARNESS` lines, stops both processes, and exits with the
exit code of the player. The work folder keeps `build.log`, `player.log`, `gateway.log` and
`adapter.log`. Editors are looked up in `~/Unity/Hub/Editor`, or in `UNITY_EDITORS`.

`OPENROIS_HARNESS_STRIPPING` overrides the level, with a name of `ManagedStrippingLevel` such as
`Medium`. Mono stays below High because at High every read through `System.Text.Json` fails on Mono
with a `FieldAccessException`. IL2CPP passes at High.

## Android

The gateway address is set at build time, in `harness.json` in StreamingAssets, because a launched
app has no environment and a device reaches the gateway over the LAN. Use the address of this
machine on that network:

```bash
OPENROIS_GATEWAY_URL=ws://192.168.1.20:8765 \
  testing/unity-harness/run.sh /path/to/new-folder-5 6000.0.85f2 android
OPENROIS_GATEWAY_URL=ws://192.168.1.20:8765 \
  testing/unity-harness/run.sh /path/to/new-folder-6 6000.6.5f1 android
```

This builds an ARM64 IL2CPP APK with stripping High at `player/harness.apk` and stops there. To run
it, start a gateway that the LAN can reach, then install and launch the APK. The gateway does not
authenticate its peers, so bind another interface only on a network you trust.

```bash
"$OPENROIS_VENV/bin/openrois-gateway" --host 0.0.0.0 --port 8765 &
"$OPENROIS_VENV/bin/python" testing/mock-adapter/mock_adapter.py \
  --config testing/mock-adapter/adapter.fast.yaml --gateway-url ws://127.0.0.1:8765 &

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
| `Assets/HarnessRunner.cs` | The checks. It starts itself after the scene loads, so the scene stays empty |
| `Assets/Editor/HarnessBuild.cs` | The batch mode build: copies the fixtures to StreamingAssets, makes the scene, sets the player |
| `Packages/manifest.json` | The SDK as `file:../../../sdk/unity` |
| `run.sh` | Copies, builds, starts the gateway and runs the player |

The harness declares no class of its own for `System.Text.Json`, and it keeps no `link.xml` of its
own. High stripping removes the members of a class that only reflection reaches, so such a class
would need `[Preserve]`. Any `link.xml` here could also hide a gap in the one the SDK ships, which
is the one a user's player depends on.
