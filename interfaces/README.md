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
├── typescript/  # TypeScript types for the web, generated from the schema
└── fixtures/    # Wire messages and test vectors that all three packages read
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
never hand-written, except for what a schema cannot describe:

| File | Contents |
|------|----------|
| `typescript/src/condition.ts` | The CQL2-Text parser, matcher and builders |
| `typescript/src/values.ts` | The string forms of typed values |
| `typescript/src/**/index.ts` | The barrels |
| `csharp/src/OpenRoIS.Interfaces/Condition.cs` | The condition builders |
| `csharp/src/OpenRoIS.Interfaces/Values.cs` | The string forms of typed values |
| `csharp/src/OpenRoIS.Interfaces/IsExternalInit.cs` | The type `init` properties need on `netstandard2.1` |

`fixtures/wire.json` holds real messages from a gateway, recorded by
`testing/conformance/capture.py`. `fixtures/conditions.json` and `fixtures/values.json` give
each helper below an exact input and output, and `fixtures/value-edges.json` holds the edges
they cannot hold, with the differences between the languages. Each package reads all of them
in its tests, so the languages cannot drift apart.

## Packages

| Package | Language | Version | Role | Where |
|---------|----------|---------|------|-------|
| `openrois-interfaces` | Python 3.12+ | 0.1.0a6 | Source of truth | PyPI |
| `@openrois/interfaces` | TypeScript (ESM) | 0.1.0-alpha.6 | Generated | npm |
| `OpenRoIS.Interfaces` | C# (netstandard2.1) | 0.1.0-alpha.6 | Generated | Inside the Unity package |

One tag, `interfaces-v0.1.0-alpha.6`, releases all three at the same version. The C# types
are not on NuGet: they ship inside the Unity package `org.openrois.sdk`, as a precompiled
assembly. Each package README describes how to install it, and how to use it from a clone.
The GitHub release of a tag carries the wheel, the npm tarball and the `.nupkg` as assets.

## What Is Covered

The framework types are complete: return codes, results, parameters, arguments, command
units with branches, and component and engine profiles. The Python and TypeScript packages
have the profile constants of all 18 standard profiles. The Python package also reads and
writes RoIS XML: component profiles, engine profiles and bundles, and command unit
sequences, in the `XML-Profiles.xsd` form. Its declaration API (`ComponentDeclaration`,
`Param`, `Command`, `Query`, `Event`) declares the profile of a component type of your own
and writes it as XML. Both stay in Python by design, because only engines and components need them.

The method catalog covers the service side. It has a params and a result model for every
method of SystemIF, CommandIF, QueryIF and EventIF, the method names, the notifications an
engine sends to a service application, the standard command names, and the JSON-RPC error
codes, generated from one table in `schema/catalog.json`. Streaming has no interface of its
own: the AudioStreaming and VideoStreaming profiles carry it over the other four.

OpenRoIS adds to RoIS in a few places, for example the component profiles in the
`get_profile` result and the `rois.system.profile_changed` notification. Every addition is
optional for a client, and the Python `EXTENSIONS` registry lists each one with its reason.
Section 17 of [docs/rois-reference.md](../docs/rois-reference.md) describes the wire
binding, the extension policy and each extension.

Every `condition` is a string in a subset of CQL2-Text (OGC 21-065r2), for example
`component_ref = 'reachy_real/head'`. `Result`, `Parameter` and `Argument` carry a value as
a string in the form of its `data_type_ref`, described in section 17.6 of
[docs/rois-reference.md](../docs/rois-reference.md). All three languages have helpers for
both, so a client does not need to write either form by hand:

| Helper | Python | TypeScript | C# |
|--------|--------|------------|----|
| Build a condition | `eq`, `like`, `all_of`, `quote`, `component_ref`, `component_type`, `component_type_urn` in `condition` | `eq`, `like`, `allOf`, `quote`, `componentRef`, `componentType`, `componentTypeUrn` in `condition` | `Eq`, `Like`, `AllOf`, `Quote`, `ComponentRef`, `ComponentType`, `ComponentTypeUrn` on `Condition` |
| Parse and match a condition | `parse_condition`, `Condition` | `parseCondition`, `Condition` | None, because a Unity client only sends conditions |
| Encode and decode a value | `encode_value`, `decode_value` in `values` | `encodeValue`, `decodeValue` in `values` | `Encode`, `Decode` on `RoISValues` |

Profile constants exist for all 17 basic RoIS HRI Components and for the RoIS_Common
profile they include, from `AUDIO_STREAMING_PROFILE` to `VIDEO_STREAMING_PROFILE`, in
Python and TypeScript. They are not in C# by design, because no component is written in C#.
The 18 `*_URN` constants of the standard component types exist only in Python, by design:
TypeScript and C# pass an authority and a code to their `component_type` builder instead.

Typed per-component message models exist for 4 components:

| Component | Typed messages |
|-----------|----------------|
| `PersonDetection` | Event `person_detected`, `component_status` |
| `Navigation` | Command `set_parameter`, Query `get_parameter`, Event `reached_target`, `component_status` |
| `Reaction` | Command `set_parameter`, Query `get_parameter`, `component_status` |
| `SystemInformation` | Queries `robot_position`, `engine_status` |

A profile constant is the full profile of the type: its XML profile with the RoIS_Common
messages it includes, and its RoSO function. A component declares the constant of its type
and implements a part of it, and the engine serves the part it implements. The Python
package generates the constants from the XML profiles and `OWL.ttl`, and exports them to
`schema/profiles.json`, from which the TypeScript constants are generated.

Components without a typed model still work: they carry generic `Result` lists validated
against their declared profile. Typed models for the other components arrive with the
full component library of `v1.0` ([roadmap](https://github.com/openrois/openrois/blob/dev/docs/roadmap.md)).

## Traceability

Every type stays traceable to the normative RoIS files: the IDL, the XML component
profiles, and `XML-Profiles.xsd`. Field names are never invented. When the IDL and the XML
profile disagree, the XML profile wins and the divergence is recorded in
[docs/rois-reference.md](../docs/rois-reference.md).

## License

Apache-2.0. See each package's `LICENSE` file.
