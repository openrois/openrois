# About OpenRoIS SDK

Use the OpenRoIS SDK package to connect a Unity application to an OpenRoIS gateway and
drive physical robots, virtual avatars, and AI services through the standard interfaces
of the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). The same calls work
for a physical robot and for a virtual character, which lets one Unity application serve
as the front end of either.

This version of the package is an alpha: pre-1.0, with an unstable API. See the
[roadmap](https://openrois.org/docs/project/roadmap).

# Installing OpenRoIS SDK

The package is not on a registry. Add it by Git URL, with the tag of the release, in the
Package Manager window or in `Packages/manifest.json`. Unity needs Git on the machine:

```json
{
  "dependencies": {
    "org.openrois.sdk": "https://github.com/openrois/openrois.git?path=sdk/unity#sdk-unity-v0.1.0-alpha.1"
  }
}
```

For general guidance, see the Unity Manual on
[installing a package from a Git URL](https://docs.unity3d.com/Manual/upm-ui-giturl.html).

# Using OpenRoIS SDK

`RoISClient` has one method per operation of the RoIS method catalog, and one client is
one session. Connect from the main thread, so that listeners run on it:

```csharp
await using var client = await RoISClient.ConnectAsync("ws://127.0.0.1:8765");
const string nav = "mock/navigation";

// Listen before the call, because a command can end before the reply is read.
var ended = new Dictionary<string, CompletedStatus>();
client.On(RoISNotifications.Completed, (CompletedParams p) => ended[p.CommandId] = p.Status);

await client.BindAsync(nav);
var ids = await client.ExecuteAsync(new[] { new CommandUnit(nav, RoISCommandTypes.Start) });
// Later: ended[ids[0]] is OK once the navigation has ended.
await client.ReleaseAsync(nav);
```

The **Navigation Session** sample runs this session against the mock adapter. The
[README](https://github.com/openrois/openrois/blob/dev/sdk/unity/README.md) covers the
whole API, the listeners, the exceptions and the mobile lifecycle. The
[wire protocol reference](https://openrois.org/docs/reference/wire-protocol) lists every
RoIS method, its parameters, and its implementation status in the engine.

# Technical Details

## Requirements

This version of OpenRoIS SDK is compatible with the following versions of the Unity
Editor:

- Unity 6000.0 and later

The targets are desktop, mobile and VR headsets. WebGL is not a target, because the
client runs on `ClientWebSocket`. The README lists what has been run for this release:
Linux players and the Editor. The package has no package dependencies. Running its Unity
tests needs `com.unity.test-framework` in the project.

## Known Limitations

OpenRoIS SDK version 0.1.0-alpha.1 includes the following known limitations:

- Android builds, but the run on a device is pending, so Android and VR headsets are
  unconfirmed. iOS has not been built. Windows and macOS players have not been run.
- `wss://` has not been exercised. Every run so far used `ws://`.
- A project that already contains an assembly named like one in `Runtime/Plugins` does
  not compile with this package.
- Mono players with Managed Stripping Level High fail at runtime with a
  `FieldAccessException` inside `System.Text.Json`. Use Medium or lower on Mono. IL2CPP
  works at High.
- An anonymous object passed to `client.Transport.SendAsync` goes out as `{}` at
  stripping High.
- There is no automatic reconnect. A suspended mobile app can lose its socket, and the
  application then connects again and binds again.
- No authentication. The OpenRoIS gateway does not authenticate connections in the alpha
  releases. Use it on trusted networks only.

## Package Contents

| Location | Description |
|----------|-------------|
| `Runtime` | `RoISClient`, its listeners, and the exceptions |
| `Runtime/Transport` | `WebSocketTransport`, on `ClientWebSocket` |
| `Runtime/JsonRpc` | The JSON-RPC 2.0 builder, parser, and message types |
| `Runtime/Plugins` | `OpenRoIS.Interfaces`, `System.Text.Json`, and the dependencies of `System.Text.Json` that Unity does not provide |
| `Runtime/link.xml` | Keeps the assemblies that `System.Text.Json` reads by reflection in stripped builds |
| `Editor` | Hands `Runtime/link.xml` to the managed code linker, and ends every client with Play Mode |
| `Tests/Runtime` | Unity Test Framework tests for the builder and the parser |
| `Samples~/Example` | The Navigation Session sample |

## Document Revision History

| Date | Reason |
|------|--------|
| November 7, 2026 | Rewritten for `RoISClient` |
| September 18, 2026 | Document created for package version 0.1.0-alpha.1 |
