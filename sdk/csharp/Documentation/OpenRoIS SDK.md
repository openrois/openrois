# About OpenRoIS SDK

Use the OpenRoIS SDK package to connect a Unity application to an OpenRoIS gateway and
drive robots, avatars, and AI services through the standard interfaces of the
[OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). The same calls work for a
physical robot and for a virtual character, which lets one Unity application serve as
the front end of either.

This version of the package is an alpha. It contains `RoISClient`, the System, Command,
Query, and Event interfaces as async methods with notifications as C# events, and the
JSON-RPC 2.0 layer underneath. The Streaming Interface is planned. See the
[roadmap](https://openrois.org/docs/project/roadmap).

# Installing OpenRoIS SDK

The package is not published to a registry yet. Add it from a local clone of the
[OpenRoIS repository](https://github.com/openrois/openrois) by editing
`Packages/manifest.json`:

```json
{
  "dependencies": {
    "org.openrois.sdk": "file:../../openrois/sdk/csharp"
  }
}
```

For general guidance, see the Unity Manual on
[installing a package from a local folder](https://docs.unity3d.com/Manual/upm-ui-local.html).

# Using OpenRoIS SDK

`OpenRoIS.Sdk.RoISClient` is the entry point:

- `RoISClient.ConnectAsync(url, options)` opens the WebSocket and performs the RoIS
  connect handshake. `ClientOptions.Token` presents a bearer token when the gateway
  authenticates.
- `SearchAsync`, `GetProfileAsync`, `QueryAsync`, `BindAsync`, `SetParameterAsync`,
  `ExecuteAsync`, `SubscribeAsync`, and the other operations mirror the RoIS interfaces.
- `EventReceived`, `CommandCompleted`, `ErrorNotified`, `ProfileChanged`, and `Closed` are
  raised on the thread that called `ConnectAsync`, the main thread from a MonoBehaviour.

`Samples/Example/SampleExample.cs` shows the whole flow in a scene. The JSON-RPC 2.0 layer
(`OpenRoIS.Sdk.JsonRpc`) remains available for custom transports.

The [wire protocol reference](https://openrois.org/docs/reference/wire-protocol) lists
every RoIS method, its parameters, and its implementation status in the engine.

# Technical Details

## Requirements

This version of OpenRoIS SDK is compatible with the following versions of the Unity
Editor:

- Unity 6.5 and later

The package depends on `com.unity.test-framework` for its tests only.

## Known Limitations

OpenRoIS SDK version 0.1.0-alpha.3 includes the following known limitations:

- The Streaming Interface is not implemented yet.
- WebGL builds cannot use `ClientWebSocket`; a browser transport is planned.
- Authentication is off by default on the gateway. Pass `ClientOptions.Token` when it is on.

## Package Contents

| Location | Description |
|----------|-------------|
| `Runtime` | `RoISClient`, its value types, and the JSON-RPC 2.0 layer under `Runtime/JsonRpc` |
| `Tests/Runtime` | Unity Test Framework tests for the JSON-RPC layer |
| `DotNetTests~` | Plain .NET tests of the client, ignored by Unity |
| `Samples/Example` | A MonoBehaviour that discovers components, subscribes, and commands |

## Document Revision History

| Date | Reason |
|------|--------|
| September 18, 2026 | Document created for package version 0.1.0-alpha.3 |
