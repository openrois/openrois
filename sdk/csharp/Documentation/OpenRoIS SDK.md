# About OpenRoIS SDK

Use the OpenRoIS SDK package to connect a Unity application to an OpenRoIS gateway and
drive robots, avatars, and AI services through the standard interfaces of the
[OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). The same calls work for a
physical robot and for a virtual character, which lets one Unity application serve as
the front end of either.

This version of the package is an alpha. It contains the JSON-RPC 2.0 layer used by the
protocol. The high-level `RoISClient` is in progress. See the
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

Everything currently available lives in the `OpenRoIS.Sdk.JsonRpc` namespace.

- `JsonRpcBuilder.CreateRequest(id, method, parameters)` and
  `JsonRpcBuilder.CreateNotification(method, parameters)` produce wire-ready strings.
- `JsonRpcParser.Parse(json)` classifies an incoming string as a request, response, error,
  or notification and exposes the typed message.

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

- No high-level RoIS client yet. Applications build and parse JSON-RPC messages and
  manage their own WebSocket.
- No authentication. The OpenRoIS gateway does not authenticate connections in the alpha
  releases. Use it on trusted networks only.

## Package Contents

| Location | Description |
|----------|-------------|
| `Runtime/JsonRpc` | The JSON-RPC 2.0 builder, parser, and message types |
| `Tests/Runtime` | Unity Test Framework tests for the builder and the parser |
| `Samples/Example` | Placeholder sample, to be replaced by a RoIS client sample |

## Document Revision History

| Date | Reason |
|------|--------|
| September 18, 2026 | Document created for package version 0.1.0-alpha.3 |
