# OpenRoIS SDK for Unity

The Unity client SDK of [OpenRoIS](https://openrois.org/), an open-source middleware implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). Shipped as the Unity package `org.openrois.sdk` (assembly `OpenRoIS.Sdk`), for Unity 6000.0 and later.

Connect to an OpenRoIS engine, discover the components of every connected physical robot, virtual avatar, or AI service, and drive them through the standard RoIS interfaces. Listeners run on the Unity main thread, with no `MonoBehaviour` and no dispatcher to set up.

> **Alpha, pre-1.0, unstable API.**

## Install

The package is not on a registry. Add it by Git URL, with the tag of the release, in the Package Manager window (**Install package from git URL**) or in your project manifest. Unity needs Git on the machine for this:

```json title="Packages/manifest.json"
{
  "dependencies": {
    "org.openrois.sdk": "https://github.com/openrois/openrois.git?path=sdk/unity#sdk-unity-v0.1.0-alpha.1"
  }
}
```

The `path` selects the package in the repository, and the part after `#` is the tag. Without a tag, Unity follows the default branch.

To work on the package, point the manifest at a local clone instead, with `"file:../../openrois/sdk/unity"`.

## Platforms

The targets are desktop, mobile and VR headsets. WebGL is not a target, because the client runs on `ClientWebSocket`, which does not work in a WebGL player.

A target is not yet a proof. This is what has been run for this release:

| Player | Scripting backend | Unity | State |
|--------|-------------------|-------|-------|
| Linux | IL2CPP, stripping High | 6000.0, 6000.3, 6000.6 | Run in a real player |
| Linux | Mono | 6000.0, 6000.3 | Run in a real player |
| Editor Play Mode on Linux | Mono | 6000.0, 6000.3, 6000.6 | Run with domain reload off, and with it on for 6000.0 and 6000.6 |
| Android ARM64 | IL2CPP, stripping High | 6000.0, 6000.6 | Builds. The run on a device is pending |
| VR headsets | | | Not run. A standalone headset takes the Android ARM64 build, so it waits on the same run |
| iOS | | | Not built |
| Windows, macOS | | | Not run |

Until the device run is done, treat Android and headsets as unconfirmed. Public sources do not settle how `ClientWebSocket` behaves there.

Unity adds the Android internet permission when it sees its own networking classes, and `ClientWebSocket` is not one of them. An Android build needs **Internet Access** set to **Require** in the Player settings, which is `PlayerSettings.Android.forceInternetPermission`.

## Usage

```csharp
using System;
using System.Collections.Generic;
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Profiles;
using OpenRoIS.Interfaces.Service;
using OpenRoIS.Sdk;
using UnityEngine;

public sealed class Navigator : MonoBehaviour
{
    private async void Start()
    {
        await using var client = await RoISClient.ConnectAsync("ws://127.0.0.1:8765");

        // Find a component by type, and select it by ref in later calls.
        var found = await client.SearchAsync(
            Condition.ComponentType(new RoISIdentifierType("Navigation", "OMG")));
        var nav = found[0];
        var target = Condition.ComponentRef(nav);

        // Read state.
        var status = await client.QueryAsync("component_status", target);
        Debug.Log(status[0].Value);

        // React to events.
        client.On(RoISNotifications.NotifyEvent, (NotifyEventParams e) => Debug.Log(e.EventType));
        await client.SubscribeAsync("reached_target", target);

        // Record how each command ends, before running any.
        var statuses = new Dictionary<string, CompletedStatus>();
        client.On(RoISNotifications.Completed, (CompletedParams c) => statuses[c.CommandId] = c.Status);

        // Reserve, configure, command, release.
        await client.BindAsync(nav);
        await client.SetParameterAsync(
            nav, new[] { new Parameter("target_positions", "string[]", "[\"kitchen\"]") });
        var ids = await client.ExecuteAsync(new[] { new CommandUnit(nav, RoISCommandTypes.Start) });
        // Later: statuses[ids[0]] is OK once the navigation has ended.
        await client.ReleaseAsync(nav);
    }
}
```

An `async void` method has no caller, so a real script catches failures in it. The sample does.

## Sample

The **Navigation Session** sample runs connect, bind, execute and the completed notification against the mock adapter. Import it from the **Samples** tab of the package in the Package Manager window, and attach `NavigationSession` to a GameObject. Then start a gateway with the mock adapter behind it, from the repository root, and enter Play Mode:

```bash
docker compose up --build
```

## Waiting for a Command

RoIS has no operation that waits for a command, so neither does the client. `ExecuteAsync` returns as soon as the engine accepts the commands. Each command ends later, with a `rois.command.completed` notification that names its id. `SetParameterAsync` works the same way.

A command that ends at once can complete before the reply reaches your code, so a listener added after `ExecuteAsync` can miss it. The recipe has three steps:

1. Add the listener before the call, once for the whole session.
2. Record each status by `CommandId`.
3. Read the status with the ids in the reply.

The usage above does this. To wait inside an `async` method, read the record once per frame, as the sample does, and stop when `close` fires. The listener and the method both run on the main thread, so the record needs no lock.

## API

`RoISClient` has one method per operation of the RoIS method catalog. Each takes the operation's IDL parameters in IDL order, returns a `Task` of the result's out parameters as generated models, and takes an optional `CancellationToken` last, which stops waiting for the reply and leaves the client working.

| RoIS interface | Methods |
|----------------|---------|
| System | `RoISClient.ConnectAsync(url, requestTimeout, connectTimeout, cancellationToken)`, `DisconnectAsync()`, `GetProfileAsync(condition)`, `GetErrorDetailAsync(errorId, condition)` |
| Command | `SearchAsync(condition)`, `BindAsync(componentRef)`, `BindAnyAsync(condition)`, `ReleaseAsync(componentRef)`, `GetParameterAsync(componentRef)`, `SetParameterAsync(componentRef, parameters)`, `ExecuteAsync(commandUnitList)`, `GetCommandResultAsync(commandId, condition)` |
| Query | `QueryAsync(queryType, condition)` |
| Event | `SubscribeAsync(eventType, condition)`, `UnsubscribeAsync(subscribeId)`, `GetEventDetailAsync(eventId, condition)` |

A streaming component is driven with these same methods. Carrying its media is planned.

- `GetProfileAsync` returns an `EngineProfile` with `Profile` and `ComponentProfiles`: the engine profile and the profile of every component it lists, keyed by fully qualified ref.
- `ExecuteAsync` takes a command unit list: `CommandUnit` items that run in order, and `ConcurrentCommands` groups whose branches run at the same time, each branch in order. The commands need no command id: the engine assigns one to each, and `ExecuteAsync` returns them in order, branch by branch.
- `QueryAsync` and `SubscribeAsync` go to the one component that declares the query or event type and matches the condition.

The client does not validate params, because the generated classes do not describe their constraints. An invalid value comes back from the engine as an `RpcException`, and never reaches a component.

One client is one session. Bindings and subscriptions end with it, and there is no automatic reconnect, because a silent reconnect would hide that loss. After `close`, connect again and bind and subscribe again.

### Conditions

Every `condition` is a string in the OpenRoIS subset of CQL2-Text: `=` and `LIKE` comparisons, joined by `AND`, over `component_ref` and `component_type`. An empty string is no filter. The `Condition` builders of `OpenRoIS.Interfaces` quote values for you:

| Builder | Writes |
|---------|--------|
| `Condition.ComponentRef("reachy_real/head")` | `component_ref = 'reachy_real/head'` |
| `Condition.ComponentType(new RoISIdentifierType("Navigation", "OMG"))` | `component_type = 'urn:x-rois:def:component:OMG::Navigation'` |
| `Condition.Like(Condition.ComponentRefProperty, "reachy_real/%")` | `component_ref LIKE 'reachy_real/%'` |
| `Condition.AllOf(a, b)` | `a AND b` |

### Listening

`On(name, listener)` adds a listener and `Off(name, listener)` removes it. Listeners of catalog notifications receive the params as generated models, and `RoISNotifications` has their names.

| Name | Listener takes |
|------|----------------|
| `rois.event.notify_event` | `NotifyEventParams`, for every event of every subscription. Filter by `SubscribeId` or `EventType` |
| `rois.command.completed` | `CompletedParams`, when a command ends |
| `rois.system.notify_error` | `NotifyErrorParams`, when the engine reports an error |
| `rois.system.profile_changed` | `ProfileChangedParams`, when components join or leave |
| `close` | `(int code, string reason)`, when the connection closes, from either side |
| `error` | `Exception`, for a message that cannot be used or a listener that throws |

`ConnectAsync` captures `SynchronizationContext.Current`, and listeners run in it from then on. On the Unity main thread that is the main thread, so listeners can call Unity APIs. Call `ConnectAsync` from the main thread, because from a worker thread there is no context, and listeners run on the reader of the socket, where they must not block.

A listener that throws never stops the client: the exception goes to the `error` listeners, and the other listeners still run. With no `error` listener, a fault is logged, never thrown. In a player it goes to the player log, and in the Editor to the Console window.

### Closing

`await using` calls `DisconnectAsync` when the block ends. It is safe to call twice, in turn or overlapping, and calls that overlap share one `rois.system.disconnect`.

```csharp
await using (var client = await RoISClient.ConnectAsync("ws://127.0.0.1:8765"))
{
    await client.SearchAsync();
}
```

`close` reports the code and the reason of the peer, or one of these:

| What happened | `close` reports |
|---------------|-----------------|
| The connection dropped | 1006 |
| A message over 16 MiB | 1009 |
| The socket refused a frame, for example invalid UTF-8. The socket does not say which | 1006 with the reason `refused frame`, and an `error` event |
| The peer closed with no code | 1000, which is what the socket reports |

## Error Handling

```csharp
try
{
    await client.BindAsync("robot_1/navigation");
}
catch (RoISException failure) when (failure.ReturnCode == ReturnCode.OUT_OF_RESOURCES)
{
    // Another application holds the reservation.
}
```

| Exception | Raised when | Carries |
|-----------|-------------|---------|
| `RoISException` | A RoIS operation returns a code other than `OK` | `ReturnCode`, `Method` |
| `TransportException` | The base of the three below. Raised itself for a call on a closed client, or a result that does not match its model | |
| `RoISConnectionException` | The WebSocket cannot be opened, or closes while a request waits | `Url` |
| `RequestTimeoutException` | No reply within the request timeout | `Method`, `RequestId` |
| `RpcException` | The engine returns a JSON-RPC error: a protocol fault, such as an unknown method or invalid params | `Code`, `Data` |

`ConnectAsync` takes the timeouts as `TimeSpan` values:

```csharp
var client = await RoISClient.ConnectAsync(
    "ws://127.0.0.1:8765",
    requestTimeout: TimeSpan.FromSeconds(5),
    connectTimeout: TimeSpan.FromSeconds(2));
```

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `requestTimeout` | 30 seconds | How long a request waits for its reply |
| `connectTimeout` | 10 seconds | How long the WebSocket has to open |

## Mobile Lifecycle

A mobile operating system can suspend an app in the background, and a suspended app can lose its socket. The SDK adds nothing for this. When the connection drops, pending requests fail with a `RoISConnectionException` and the client fires `close`, which is what scenario C20 of the [conformance list](../../testing/conformance/README.md) proves on a desktop. The session is gone with its bindings and subscriptions, so the application connects again and binds again:

```csharp
private RoISClient _client;

// Set this before a deliberate DisconnectAsync, and when the script is destroyed. In the
// Editor the close from leaving Play Mode can arrive first, and that connect is refused.
private bool _leaving;

private async Task OpenSessionAsync()
{
    _client = await RoISClient.ConnectAsync(_url);
    _client.On("close", OnClosed);
    await _client.BindAsync(_navigation);
}

private async void OnClosed(int code, string reason)
{
    if (_leaving)
    {
        return;
    }
    try
    {
        await OpenSessionAsync();
    }
    catch (TransportException failure)
    {
        // The application decides when to try again.
        Debug.LogWarning(failure.Message);
    }
}
```

Listeners run on the main thread, so an app hears `close` only once its main thread runs again. The client adds no heartbeat, so a network that goes away without closing the connection can stay unnoticed, and a request that times out can be the first sign.

How a real device behaves here has not been observed yet: the device run is pending.

## The Editor

Every client ends when Play Mode ends and before an assembly reload, with one `rois.system.disconnect`, so a client never outlives Play Mode, also with domain reload off. The Editor waits at most 1 second for an engine that stopped answering, then drops the connection. A client opened from an Editor tool outside Play Mode ends at those moments as well, because the runtime assembly cannot tell the two apart.

Scripts and listeners keep running until the Editor is back in Edit Mode, so until then `ConnectAsync` fails with a `RoISConnectionException`, and a `close` listener that connects again opens nothing. From Edit Mode on, a connect counts as one from an Editor tool, so a script that reconnects has to stop once it is destroyed, as [Mobile Lifecycle](#mobile-lifecycle) shows.

`close` can arrive during or after the exit from Play Mode, before or after `OnDestroy`, and the order changes from one run to the next. So a listener has to check that its object still exists before it touches it, with `if (this == null) return;` in a `MonoBehaviour`. Otherwise the `MissingReferenceException` goes to the `error` listeners, or to the Console as an error.

## The Transport

`client.Transport` is the `WebSocketTransport` under the client, for JSON-RPC methods outside the catalog. Nothing sent through it is validated.

```csharp
var parameters = new Dictionary<string, object> { ["level"] = 3 };
JsonElement result = await client.Transport.SendAsync("vendor.custom.method", parameters);
```

Do not pass an anonymous object. Stripping at High removes its getters, and it goes out as `{}`.

The JSON-RPC layer under it, `JsonRpcBuilder` and `JsonRpcParser` in `OpenRoIS.Sdk.JsonRpc`, stays public for an application that manages its own socket.

## Bundled Assemblies

The RoIS message types live in [`OpenRoIS.Interfaces`](../../interfaces/csharp/README.md) and are generated from the canonical JSON Schema. Unity 6000.0 and 6000.3 have no `System.Text.Json`, so the package carries what it needs in `Runtime/Plugins`. Unity 6000.6 ships version 8.0 in its class library and discards other copies, which is why the package stays on version 8:

| Assembly | Version | Auto referenced |
|----------|---------|-----------------|
| `OpenRoIS.Interfaces` | Built from `interfaces/csharp` | Yes |
| `System.Text.Json` | 8.0.6 | Yes, the SDK API exposes `JsonElement` |
| `System.Text.Encodings.Web` | 8.0.0 | No |
| `Microsoft.Bcl.AsyncInterfaces` | 8.0.0 | No |
| `System.Runtime.CompilerServices.Unsafe` | 6.0.0 | No |

A project that already contains an assembly with one of these names does not compile with this package, because Unity refuses two precompiled assemblies with the same name. `Runtime/link.xml` keeps the assemblies that `System.Text.Json` reads by reflection from being stripped, and the `OpenRoIS.Sdk.Editor` assembly hands it to the linker. Licenses are in [Third Party Notices](Third%20Party%20Notices.md).

**Mono stripping limit:** Mono players need a Managed Stripping Level of Medium or lower. At High they fail at runtime with a `FieldAccessException` inside `System.Text.Json`. IL2CPP works at High.

Rebuild the assemblies after a change to the C# interface types or to their `System.Text.Json` version. This needs Python 3 and the .NET SDK pinned in `scripts~/global.json`:

```bash
python3 sdk/unity/scripts~/bundle_dlls.py
```

CI runs the script with `--check` and fails if the committed files differ from a fresh build. The `.meta` files come from the script as well, with stable GUIDs.

## Tested Versions

The wire has no version handshake, so a mismatch shows only when a message carries a field the other side does not know. This release is tested against these versions together, which `testing/conformance/frozen.txt` pins. The package carries its `OpenRoIS.Interfaces` inside it, so that version comes with the release:

| `org.openrois.sdk` | `OpenRoIS.Interfaces` | `openrois-gateway` | `openrois-engine` | `openrois-interfaces` | `openrois-components-core` |
|---|---|---|---|---|---|
| 0.1.0-alpha.1 | 0.1.0-alpha.6 | 0.1.0a1 | 0.1.0a2 | 0.1.0a6 | 0.1.0a1 |

## Development

`Tests~` is a `dotnet test` project that needs no Unity. It compiles `Runtime` as a Unity Editor does, with C# 9 on `netstandard2.1`, against the assemblies in `Runtime/Plugins`, and runs the [conformance list](../../testing/conformance/README.md). C01 to C17 need a live gateway with the mock adapter behind it, and are skipped without `OPENROIS_GATEWAY_URL`. C18 to C21 start `testing/conformance/scripted_server.py` with `python3`, which needs the `websockets` package.

```bash
docker compose up --build -d   # from the repository root
pip install websockets
cd sdk/unity/Tests~
OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 dotnet test
```

[`testing/unity-harness`](../../testing/unity-harness/README.md) proves the bundled types and `RoISClient` in real players, and the end of a client with Play Mode in the Editor. Never open the package folder in Unity directly, because Unity writes `.meta` files and a `Library` folder into a `file:` package. `run.sh` works on a copy.

`Tests/Runtime` holds Unity Test Framework tests of the JSON-RPC layer. They are PlayMode tests, since their assembly is not limited to the Editor. To run them, install `com.unity.test-framework` in your project and list the package under `"testables"` in `Packages/manifest.json`. Then use the Unity Test Runner window, or batch mode:

```bash
Unity -batchmode -runTests -testPlatform PlayMode -projectPath <your project>
```

## License

Apache-2.0. See [LICENSE.md](LICENSE.md).
