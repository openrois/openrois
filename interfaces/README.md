# Interfaces

Transport-independent [RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) interface
types, generated across three language stacks from a single source.

An application written in TypeScript, an engine written in Python, and a Unity client
written in C# all speak the same wire contract, because all three read from the same JSON
Schema.

## Structure

```
interfaces/
├── python/      # Source of truth, hand-authored Pydantic models
├── schema/      # Canonical JSON Schema wire contract, generated from Python
├── csharp/      # C# types for Unity, generated from the schema
└── typescript/  # TypeScript types for the web, generated from the schema
```

## Pipeline

```
Python (Pydantic) ──export_schema.py──► JSON Schema ──Generator──► C#
                                          │
                                          ├──generate.ts──► TypeScript
                                          └── manifest.json (module to file map)
```

1. **Author** the Pydantic models in `python/src/openrois/interfaces/`.
2. **Export** to JSON Schema: `cd python && python scripts/export_schema.py`.
3. **Generate** C#: `cd csharp && dotnet run --project scripts/Generator/Generator.csproj` (reads `../schema` by default).
4. **Generate** TypeScript: `cd typescript && npx tsx scripts/generate.ts`.

The schema drift test (`python/tests/test_schema_drift.py`) verifies that the committed
schemas still match what the Pydantic models produce. The C# and TypeScript sources are
never hand-written, except `typescript/src/bus.ts`, because JSON Schema cannot express a
behavioral interface.

## Packages

| Package | Language | Version | Role |
|---------|----------|---------|------|
| `openrois-interfaces` | Python 3.12+ | 0.1.0a3 | Source of truth |
| `@openrois/interfaces` | TypeScript (ESM) | 0.1.0-alpha.3 | Generated |
| `OpenRoIS.Interfaces` | C# (netstandard2.1) | 0.1.0-alpha.3 | Generated |

None are published yet. Install them from a clone, as each package README describes.

## What Is Covered

The framework types are complete: return codes, results, parameters, arguments, command
units, component and engine profiles, event envelopes, and the `ComponentContract` request
and response models.

Typed per-component message models exist for 4 of the 17 basic RoIS HRI Components:

| Component | Typed messages |
|-----------|----------------|
| `PersonDetection` | Event `person_detected`, `component_status` |
| `Navigation` | Command `set_parameter`, Query `get_parameter`, Event `reached_target`, `component_status` |
| `Reaction` | Command `set_parameter`, Query `get_parameter`, `component_status` |
| `SystemInformation` | Queries `robot_position`, `engine_status` |

Components without a typed model still work: they carry generic `Result` lists validated
against their declared profile. The remaining components arrive with the full component
library in [Phase 10](https://openrois.org/docs/project/roadmap).

## Traceability

Every type stays traceable to the normative RoIS files: the IDL, the XML component
profiles, and `XML-Profiles.xsd`. Field names are never invented. When the IDL and the XML
profile disagree, the XML profile wins and the divergence is recorded in
[docs/rois-reference.md](../docs/rois-reference.md).

## License

Apache-2.0. See each package's `LICENSE` file.
