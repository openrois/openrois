# OpenRoIS SDK for Unity

C# client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware
implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). Shipped as
the Unity package `org.openrois.sdk` (assembly `OpenRoIS.Sdk`), targeting Unity 6.5 and
later as declared in its package manifest, and usable from any .NET runtime that provides
`System.Net.WebSockets` (.NET Standard 2.1).

> **Alpha, pre-1.0, unstable API.** Not yet listed on a package registry. Install from a
> clone or a Git URL as shown below.

## What Is Available

| Type | Namespace | Purpose |
|------|-----------|---------|
| `RoISClient` | `OpenRoIS.Sdk` | The client: the System, Command, Query, and Event interfaces as async methods, notifications as events |
| `RoISValue`, `ExecuteResult`, `EventNotification`, `CommandCompletion`, `ErrorNotification` | `OpenRoIS.Sdk` | The values exchanged with the gateway |
| `RoISException`, `RpcException` | `OpenRoIS.Sdk` | A RoIS return code other than `OK`, a JSON-RPC error object |
| `ClientOptions` | `OpenRoIS.Sdk` | Token, request timeout, callback context |
| `JsonRpcBuilder`, `JsonRpcParser` | `OpenRoIS.Sdk.JsonRpc` | The JSON-RPC 2.0 layer underneath |

The Streaming Interface is planned. The generated RoIS message types live in
[`OpenRoIS.Interfaces`](../../interfaces/csharp/README.md) for applications that want
typed models on top of `RoISValue`.

## Install

Point your Unity project manifest at this directory (from a clone) or at the repository
(Git URL):

```json title="Packages/manifest.json"
{
  "dependencies": {
    "org.openrois.sdk": "https://github.com/openrois/openrois.git?path=sdk/csharp"
  }
}
```

## Usage

```csharp
using OpenRoIS.Sdk;

var client = await RoISClient.ConnectAsync("ws://localhost:8765");

// Discover, then pick a component by type.
var refs = await client.SearchAsync();
var nav = refs.Find(r => r.Contains("Navigation"));

// Read state.
var status = await client.QueryAsync(nav, "component_status");

// React to events and completions. Callbacks run on the thread that called
// ConnectAsync (Unity's main thread when called from a MonoBehaviour).
client.EventReceived += e => Debug.Log($"{e.EventType}: {e.Results.Count} results");
client.CommandCompleted += c => Debug.Log($"{c.CommandId} {c.Status}");
await client.SubscribeAsync(nav, "reached_target");

// Reserve, command, release.
await client.BindAsync(nav);
var executed = await client.ExecuteAsync(nav);
await client.ReleaseAsync(nav);

await client.DisconnectAsync();
```

A gateway that authenticates takes the token through `ClientOptions.Token`, presented as
an `Authorization: Bearer` header at the WebSocket upgrade.

| RoIS interface | Methods |
|----------------|---------|
| System | `ConnectAsync()`, `DisconnectAsync()`, `GetProfileAsync()`, `GetErrorDetailAsync()` |
| Command | `SearchAsync()`, `BindAsync()`, `BindAnyAsync()`, `ReleaseAsync()`, `GetParameterAsync()`, `SetParameterAsync()`, `ExecuteAsync()`, `GetCommandResultAsync()` |
| Query | `QueryAsync()` |
| Event | `SubscribeAsync()`, `UnsubscribeAsync()`, `GetEventDetailAsync()` |
| Streaming | Planned |

| Event | Raised for |
|-------|-----------|
| `EventReceived` | Every `rois.event.notify` for this client's subscriptions |
| `CommandCompleted` | `rois.command.completed` for a command this client issued |
| `ErrorNotified` | `rois.system.notify_error` |
| `ProfileChanged` | `rois.system.profile_changed`, an adapter connected or left |
| `Closed` | The connection closed |

`Samples/Example/SampleExample.cs` is a `MonoBehaviour` that runs this flow in a scene.

## Tests

`DotNetTests~` is a plain .NET test project that compiles the runtime sources and drives
the client against an in-process fake gateway, so the client is verified without the
Unity editor (`dotnet test DotNetTests~`). Unity ignores the folder because of the `~`
suffix. `Tests/Runtime` holds the Unity Test Framework tests of the JSON-RPC layer.

## License

Apache-2.0. See the [LICENSE](../../LICENSE) of the repository.
