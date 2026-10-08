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
never hand-written, except `typescript/src/condition.ts`, the CQL2-Text parser, and the
TypeScript `index.ts` barrels.

## Packages

| Package | Language | Version | Role |
|---------|----------|---------|------|
| `openrois-interfaces` | Python 3.12+ | 0.1.0a4 | Source of truth |
| `@openrois/interfaces` | TypeScript (ESM) | 0.1.0-alpha.4 | Generated |
| `OpenRoIS.Interfaces` | C# (netstandard2.1) | 0.1.0-alpha.4 | Generated |

None are published yet. Install them from a clone, as each package README describes.

## What Is Covered

The framework types are complete: return codes, results, parameters, arguments, command
units, and component and engine profiles, with the profile constants of the basic
components the package models.

The method catalog covers the service side. It has a params and a result model for every
method of SystemIF, CommandIF, QueryIF and EventIF, the method names, the notifications an
engine sends to a service application, the standard command names, and the JSON-RPC error
codes, generated from one table in `schema/catalog.json`. The Streaming interface is not
modelled.

OpenRoIS adds to RoIS in a few places, for example the component profiles in the
`get_profile` result and the `rois.system.profile_changed` notification. Every addition is
optional for a client, and the Python `EXTENSIONS` registry lists each one with its reason.
Section 17 of [docs/rois-reference.md](../docs/rois-reference.md) describes the wire
binding, the extension policy and each extension.

Every `condition` is a string in a subset of CQL2-Text (OGC 21-065r2), for example
`component_ref = 'reachy_real/head'`. The Python `condition` module and its TypeScript
port parse, match and build conditions.

Profile constants exist for 5 of the 17 basic RoIS HRI Components and for the RoIS_Common
profile they include, and typed per-component message models for 4 of them:

| Component | Profile constant | Typed messages |
|-----------|------------------|----------------|
| RoIS_Common | `ROIS_COMMON_PROFILE` | |
| `PersonDetection` | `PERSON_DETECTION_PROFILE` | Event `person_detected`, `component_status` |
| `Navigation` | `NAVIGATION_PROFILE` | Command `set_parameter`, Query `get_parameter`, Event `reached_target`, `component_status` |
| `Reaction` | `REACTION_PROFILE` | Command `set_parameter`, Query `get_parameter`, `component_status` |
| `SpeechSynthesis` | `SPEECH_SYNTHESIS_PROFILE` | |
| `SystemInformation` | `SYSTEM_INFORMATION_PROFILE` | Queries `robot_position`, `engine_status` |

A profile constant is the full profile of the type: its XML profile with the RoIS_Common
messages it includes, and its RoSO function. A component declares the constant of its type
and implements a part of it, and the engine serves the part it implements. The Python
package defines the constants and exports them to `schema/profiles.json`, from which the
TypeScript constants are generated.

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
