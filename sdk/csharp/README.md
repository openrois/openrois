# OpenRoIS SDK for Unity

C# client SDK for [OpenRoIS](https://openrois.org/), an open-source middleware
implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). Shipped as
the Unity package `org.openrois.sdk` (assembly `OpenRoIS.Sdk`), targeting Unity 6.5 and
later as declared in its package manifest.

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
canonical JSON Schema.

## Install

Not published to a registry yet. Add the package from a local clone by pointing your
Unity project manifest at this directory:

```json title="Packages/manifest.json"
{
  "dependencies": {
    "org.openrois.sdk": "file:../../openrois/sdk/csharp"
  }
}
```

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
        // message.Notification.Method, for example "rois.event.notify".
        break;
    case JsonRpcMessageType.Error:
        // message.Error.Error.Code and .Message.
        break;
}
```

Until the high-level client lands, the
[wire protocol reference](https://openrois.org/docs/reference/wire-protocol) documents
every method, its parameters, and its implementation status.

## Tests

The package includes Unity Test Framework tests under `Tests/Runtime`. Run them from the
Unity Test Runner window, or in batch mode:

```bash
Unity -batchmode -runTests -testPlatform EditMode -projectPath <your project>
```

## License

Apache-2.0. See the [LICENSE](../../LICENSE) of the repository.
