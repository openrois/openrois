# OpenRoIS.Interfaces

![.NET Standard](https://img.shields.io/badge/.NET%20Standard-2.1-512BD4?logo=dotnet&logoColor=white)

Transport-independent [RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) interface types for C#.

This package is **generated from JSON Schema**, the canonical wire contract authored as Pydantic models in `interfaces/python/` and exported to `interfaces/schema/`. The C# types are never hand-written, so all three language stacks (Python, C#, TypeScript) stay consistent. The functions that a schema cannot describe, `Condition` and `RoISValues`, are hand-written.

Targets `netstandard2.1`, for Unity 6000.0 and later.

## Installation

> **Note:** This package is not published on NuGet. It ships inside the Unity package,
> so in Unity install the OpenRoIS SDK. Outside Unity, reference the source project or
> build from source.

### Reference the Source Project

Add a project reference in your `.csproj`:

```xml
<ItemGroup>
  <ProjectReference Include="path/to/openrois/interfaces/csharp/src/OpenRoIS.Interfaces/OpenRoIS.Interfaces.csproj" />
</ItemGroup>
```

### Build from Source

```bash
cd interfaces/csharp
dotnet build src/OpenRoIS.Interfaces/OpenRoIS.Interfaces.csproj
```

The output assembly targets `netstandard2.1`.

### Unity

The Unity package `org.openrois.sdk` bundles these types as a precompiled assembly, with
the `System.Text.Json` assemblies they need, for Unity 6000.0 and later. Add it by Git URL
in `Packages/manifest.json`:

```json
{
  "dependencies": {
    "org.openrois.sdk": "https://github.com/openrois/openrois.git?path=sdk/unity"
  }
}
```

See the [SDK README](../../sdk/unity/README.md).

## Usage

```csharp
using OpenRoIS.Interfaces;
using OpenRoIS.Interfaces.Catalog;
using OpenRoIS.Interfaces.Hri;
using System.Text.Json;

// Read and write every message with RoISJson.Options
var result = JsonSerializer.Deserialize<Result>(
    "{\"name\":\"number\",\"data_type_ref\":\"int\",\"value\":\"3\"}",
    RoISJson.Options)!;

// Type-safe enum
ReturnCode code = ReturnCode.OK;

// The params of a catalog method, with a condition from the builders
var search = new SearchParams(Condition.ComponentRef("robot_1/navigation"));

// A typed value in its string form
var targets = new Parameter(
    "target_positions", "string[]", RoISValues.Encode("string[]", new[] { "kitchen" }));
var number = (long)RoISValues.Decode(result.DataTypeRef, result.Value);
```

A model refuses each of these with `JsonException`: an unknown field, a missing required field, null in a field whose C# type is not nullable, a null list item or map value, and an empty list where the schema asks for at least one item.

An optional list or map is the exception, because its C# type is nullable. An omitted list is null, and C# reads an explicit null such as `"arguments": null` as absent, where Python and TypeScript refuse it. C# never writes that null, because `RoISJson.Options` leaves unset fields out of the message.

## Namespaces

| Namespace | Contents |
|---|---|
| `OpenRoIS.Interfaces` | Hand-written: the condition builders (`Condition`) and the string forms of typed values (`RoISValues`) |
| `OpenRoIS.Interfaces.Hri` | Core HRI types: `ReturnCode`, `Result`, `Parameter`, `Argument`, `CommandUnit`, `CommandUnitSequence`, and the serializer settings `RoISJson.Options` |
| `OpenRoIS.Interfaces.Common` | `ComponentStatus`, `StreamStatus` |
| `OpenRoIS.Interfaces.Service` | Params of the engine notifications: `NotifyErrorParams`, `CompletedParams`, `NotifyEventParams`, `ProfileChangedParams`, with `CompletedStatus` and `ErrorType` |
| `OpenRoIS.Interfaces.Profiles` | Component profile schema models |
| `OpenRoIS.Interfaces.Catalog` | Service-side method catalog: params and result models for every `rois.*` method, `RoISMethods`, `RoISMethodTypes`, the notification names and types (`RoISNotifications`, `RoISNotificationTypes`), `RoISCommandTypes`, `JsonRpcErrorCodes` |
| `OpenRoIS.Interfaces.Components` | Per-component typed message models. The profile constants and the `*_URN` constants are left out by design, because no component is written in C# |

## Generation

Every source file except `Condition.cs`, `Values.cs` and `IsExternalInit.cs` is generated from `interfaces/schema/*.schema.json` and the method table in `interfaces/schema/catalog.json`:

```bash
# Reads ../schema by default (or the directory in OPENROIS_SCHEMA_DIR).
dotnet run --project scripts/Generator/Generator.csproj
```

## License

Apache-2.0. See [LICENSE](./LICENSE).