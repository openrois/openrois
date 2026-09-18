# @openrois/interfaces

![TypeScript](https://img.shields.io/badge/TypeScript-5.4+-3178C6?logo=typescript&logoColor=white)

Transport-independent [RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) interface types for TypeScript.

This package is **generated from JSON Schema**, the canonical wire contract authored as Pydantic models in `interfaces/python/` and exported to `interfaces/schema/`. The TypeScript types are never hand-written, so all three language stacks (Python, C#, TypeScript) stay consistent.

## Installation

### npm (When Published)

```bash
npm install @openrois/interfaces
```

### From Source (Alpha, Pre-Publish)

```bash
git clone https://github.com/openrois/openrois.git
cd openrois/interfaces/typescript
npm install
npm run build
```

Then reference from your project:

```json
{
  "dependencies": {
    "@openrois/interfaces": "file:../path/to/openrois/interfaces/typescript"
  }
}
```

## Usage

```ts
import { ResultSchema, ReturnCode, ComponentContract } from "@openrois/interfaces";

// Validate a RoIS Result
const result = ResultSchema.parse({
  name: "number",
  data_type_ref: "int",
  value: "3",
});

// Type-safe enum
const code: ReturnCode = "OK";

// Implement the Component Contract
class MyAdapter implements ComponentContract {
  async discover(request) { /* ... */ }
  async invoke(request) { /* ... */ }
  async query(request) { /* ... */ }
  async subscribe(request, sink) { /* ... */ }
  async unsubscribe(subscribeId) { /* ... */ }
}
```

## Subpath Exports

| Import path | Contents |
|---|---|
| `@openrois/interfaces` | All types (re-exports everything) |
| `@openrois/interfaces/hri` | Core HRI types: `ReturnCode`, `Result`, `Parameter`, `Argument`, `CommandUnit`, `CommandUnitSequence` |
| `@openrois/interfaces/common` | `ComponentStatus`, `StreamStatus` |
| `@openrois/interfaces/service` | `CompletedStatus`, `ErrorType`, `CompletedEvent`, `NotifyErrorEvent`, `NotifyEventPayload` |
| `@openrois/interfaces/profiles` | Component profile schema models |
| `@openrois/interfaces/bus` | `ComponentContract` interface, request/response models, `EventEnvelope`, error classes |
| `@openrois/interfaces/components` | Per-component typed message models |

## Generation

The source files in `src/` (except `bus.ts` and the `index.ts` barrels) are generated from `interfaces/schema/*.schema.json`:

```bash
npm run generate   # reads ../schema/*.json → writes src/*.ts
npm run build      # generate + tsc → dist/
```

The `ComponentContract` interface and error classes in `bus.ts` are hand-written, because JSON Schema cannot represent behavioral interfaces.

## Naming

The interface was called `BusAdapter` before 0.1.0-alpha.3. `BusAdapter` and `BusAdapterError` remain as deprecated aliases for one alpha release.

## License

Apache-2.0. See [LICENSE](./LICENSE).