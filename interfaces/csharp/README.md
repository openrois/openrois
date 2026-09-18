# OpenRoIS.Interfaces

![.NET Standard](https://img.shields.io/badge/.NET%20Standard-2.1-512BD4?logo=dotnet&logoColor=white)

Transport-independent [RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) interface types for C#.

This package is **generated from JSON Schema**, the canonical wire contract authored as Pydantic models in `interfaces/python/` and exported to `interfaces/schema/`. The C# types are never hand-written, so all three language stacks (Python, C#, TypeScript) stay consistent.

Targets `netstandard2.1` for Unity 6.3+ (Mono) through Unity 6.8 (CoreCLR) compatibility.

## Installation

> **Note:** The package is not yet on NuGet or UPM. For the alpha, reference
> the source project directly or build from source.

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

The output assembly targets `netstandard2.1`, compatible with Unity 6.3+ (Mono)
through Unity 6.8 (CoreCLR).

### Unity (Future)

Once published to a UPM registry, add via `manifest.json`:

```json
{
  "dependencies": {
    "org.openrois.interfaces": "0.1.0-alpha.3"
  }
}
```

## Usage

```csharp
using OpenRoIS.Interfaces.Hri;
using OpenRoIS.Interfaces.Bus;
using System.Text.Json;

// Deserialize a RoIS Result
var result = JsonSerializer.Deserialize<Result>(
    "{\"name\":\"number\",\"data_type_ref\":\"int\",\"value\":\"3\"}")!;

// Type-safe enum
ReturnCode code = ReturnCode.OK;

// Implement the Component Contract
class MyAdapter : IComponentContract
{
    public Task<DiscoverResponse> Discover(DiscoverRequest request) { /* ... */ }
    public Task<InvokeResponse> Invoke(CommandRequest request) { /* ... */ }
    public Task<QueryResponse> Query(QueryRequest request) { /* ... */ }
    public Task<SubscribeResponse> Subscribe(SubscribeRequest request, EventSink sink) { /* ... */ }
    public Task<ReturnCode> Unsubscribe(string subscribeId) { /* ... */ }
}
```

## Namespaces

| Namespace | Contents |
|---|---|
| `OpenRoIS.Interfaces.Hri` | Core HRI types: `ReturnCode`, `Result`, `Parameter`, `Argument`, `CommandUnit`, `CommandUnitSequence` |
| `OpenRoIS.Interfaces.Common` | `ComponentStatus`, `StreamStatus` |
| `OpenRoIS.Interfaces.Service` | `CompletedStatus`, `ErrorType`, `CompletedEvent`, `NotifyErrorEvent`, `NotifyEventPayload` |
| `OpenRoIS.Interfaces.Profiles` | Component profile schema models |
| `OpenRoIS.Interfaces.Bus` | `IComponentContract` interface, request/response models, `EventEnvelope`, error classes |
| `OpenRoIS.Interfaces.Components` | Per-component typed message models |

## Generation

The source files (except `Bus.cs`) are generated from `interfaces/schema/*.schema.json`:

```bash
# Reads ../schema by default (or the directory in OPENROIS_SCHEMA_DIR).
dotnet run --project scripts/Generator/Generator.csproj
```

The `IComponentContract` interface and error classes in `Bus.cs` are hand-written, because JSON Schema cannot represent behavioral interfaces.

## Naming

The interface was called `IBusAdapter` before 0.1.0-alpha.3. `IBusAdapter` and `BusAdapterError` remain as deprecated (obsolete) names for one alpha release.

## License

Apache-2.0. See [LICENSE](./LICENSE).