# OpenRoIS SDK for Unity

The Unity SDK of [OpenRoIS](https://openrois.org/), an open-source middleware
implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). Shipped as
the Unity package `org.openrois.sdk` (assembly `OpenRoIS.Sdk`), for Unity 6000.0 and later.

> **In progress.** The JSON-RPC 2.0 layer is available. The high-level `RoISClient`,
> with callbacks marshaled to the Unity main thread, is being built. Follow
> [Phase 3 of the roadmap](https://openrois.org/docs/project/roadmap). For a complete
> client today, use the [TypeScript SDK](../typescript/README.md).

## What Is Available

| Type | Namespace | Purpose |
|------|-----------|---------|
| `JsonRpcBuilder` | `OpenRoIS.Sdk.JsonRpc` | Build JSON-RPC 2.0 request and notification strings |
| `JsonRpcParser` | `OpenRoIS.Sdk.JsonRpc` | Parse an incoming message into a request, response, error, or notification |
| `JsonRpcRequest`, `JsonRpcResponse`, `JsonRpcError`, `JsonRpcNotification`, `JsonRpcMessage` | `OpenRoIS.Sdk.JsonRpc` | Message types |

The RoIS message types themselves live in
[`OpenRoIS.Interfaces`](../../interfaces/csharp/README.md) and are generated from the
canonical JSON Schema. The package bundles them, see [Bundled Assemblies](#bundled-assemblies).

## Install

Not published to a registry yet. Add the package by Git URL, in the Package Manager
window (**Install package from git URL**) or in your Unity project manifest:

```json title="Packages/manifest.json"
{
  "dependencies": {
    "org.openrois.sdk": "https://github.com/openrois/openrois.git?path=sdk/unity"
  }
}
```

To work on the package, point the manifest at a local clone instead, with
`"file:../../openrois/sdk/unity"`.

## Usage

```csharp
using OpenRoIS.Sdk.JsonRpc;

// Build a request and send it over your WebSocket.
string request = JsonRpcBuilder.CreateRequest(
    id: "1",
    method: "rois.command.search",
    parameters: new { condition = "" });

// Parse whatever comes back.
JsonRpcMessage message = JsonRpcParser.Parse(received);
switch (message.Type)
{
    case JsonRpcMessageType.Response:
        // message.Response.Result holds the RoIS result object.
        break;
    case JsonRpcMessageType.Notification:
        // message.Notification.Method, for example "rois.event.notify_event".
        break;
    case JsonRpcMessageType.Error:
        // message.Error.Error.Code and .Message.
        break;
}
```

Until the high-level client lands, the
[wire protocol reference](https://openrois.org/docs/reference/wire-protocol) documents
every method, its parameters, and its implementation status.

## Bundled Assemblies

Unity 6000.0 and 6000.3 have no `System.Text.Json`, so the package carries what it needs in
`Runtime/Plugins`. Unity 6000.6 ships version 8.0 in its class library and discards other
copies, which is why the package stays on version 8:

| Assembly | Version | Auto referenced |
|----------|---------|-----------------|
| `OpenRoIS.Interfaces` | Built from `interfaces/csharp` | Yes |
| `System.Text.Json` | 8.0.6 | Yes, the SDK API exposes `JsonElement` |
| `System.Text.Encodings.Web` | 8.0.0 | No |
| `Microsoft.Bcl.AsyncInterfaces` | 8.0.0 | No |
| `System.Runtime.CompilerServices.Unsafe` | 6.0.0 | No |

A project that already contains an assembly with one of these names does not compile
with this package, because Unity refuses two precompiled assemblies with the same name.
`Runtime/link.xml` keeps the assemblies that `System.Text.Json` reads by reflection
from being stripped, and the `OpenRoIS.Sdk.Editor` assembly hands it to the linker. Licenses are in
[Third Party Notices](Third%20Party%20Notices.md).

Mono players need a Managed Stripping Level of Medium or lower. At High they fail at runtime
with a `FieldAccessException` inside `System.Text.Json`. IL2CPP works at High.

Rebuild the assemblies after a change to the C# interface types or to their
`System.Text.Json` version. This needs Python 3 and the .NET SDK pinned in
`scripts~/global.json`:

```bash
python3 sdk/unity/scripts~/bundle_dlls.py
```

CI runs the script with `--check` and fails if the committed files differ from a fresh
build. The `.meta` files come from the script as well, with stable GUIDs.

## Tests

The package includes Unity Test Framework tests under `Tests/Runtime`. They are PlayMode
tests, since their assembly is not limited to the Editor. To run them, install `com.unity.test-framework` in your project and list the package under
`"testables"` in `Packages/manifest.json`. Then use the Unity Test Runner window, or
batch mode:

```bash
Unity -batchmode -runTests -testPlatform PlayMode -projectPath <your project>
```

## License

Apache-2.0. See [LICENSE.md](LICENSE.md).
