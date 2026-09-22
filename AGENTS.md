# AGENTS.md

> Guide for AI coding agents working in this repository. Read this first.
> Human contributors should read [CONTRIBUTING.md](CONTRIBUTING.md).

## What This Is

OpenRoIS is an open-source middleware implementing the
[OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0) (OMG document
formal/26-06-03, June 2026). It is **alpha, pre-1.0, with an unstable API**.

What exists today:

| Area | Directory | State |
|------|-----------|-------|
| RoIS interface types (Python, JSON Schema, TypeScript, C#) | `interfaces/` | Available |
| Recursive engine, gateway process, WebSocket server and client | `core/` | Available |
| Adapter SDK (component framework) and reference components | `components/` | Available |
| TypeScript client SDK | `sdk/typescript/` | Available |
| C# client SDK for Unity | `sdk/csharp/` | Available |
| Examples: mock engine, mock adapter, avatar adapter, mixed-paradigm demo, web client, adapter template | `examples/` | Available |
| Hub management application | `apps/hub/` | Not started, scaffold only |

See [docs/roadmap.md](docs/roadmap.md) for what comes next, and
[openrois.org](https://openrois.org/) for the living documentation.

## The One Critical Rule

Types flow in one direction. **Never edit generated files by hand.**

```
Python (Pydantic) → JSON Schema → C# + TypeScript
```

- **Edit:** `interfaces/python/src/openrois/interfaces/*.py`
- **Never edit:** `interfaces/schema/`,
  `interfaces/csharp/src/OpenRoIS.Interfaces/Generated/`,
  `interfaces/typescript/src/` (except `bus.ts` and the `index.ts` barrels, which are
  hand-written)

After editing the Python models, run the full pipeline and the tests:

```bash
cd interfaces/python && python scripts/export_schema.py
cd ../typescript && npx tsx scripts/generate.ts && npm run typecheck && npm test
cd ../csharp && dotnet run --project scripts/Generator/Generator.csproj && dotnet test
```

Every interface type must stay traceable to the normative RoIS files: the IDL, the XML
component profiles, and `XML-Profiles.xsd`. Do not invent field names. When the IDL and
the XML profile disagree, follow the XML profile and document the divergence in
[docs/rois-reference.md](docs/rois-reference.md).

## Build and Test

| Stack | Directory | Commands |
|-------|-----------|----------|
| Python types | `interfaces/python` | `pip install -e ".[dev]"`, `pytest`, `mypy src/`, `ruff check src/` |
| TypeScript types | `interfaces/typescript` | `npm install`, `npm run build`, `npm test` |
| C# types | `interfaces/csharp` | `dotnet build`, `dotnet test` |
| C# SDK | `sdk/csharp` | `dotnet test DotNetTests~` (no Unity editor needed) |
| Engine core | `core` | `pip install -e ".[dev]"`, `pytest`, `mypy src/`, `ruff check src/ tests/` |
| Component framework | `components/core` | `pip install -e .` |
| TypeScript SDK | `sdk/typescript` | `npm install`, `npm run build`, `npm test` |
| Mock engine | `examples/mock-engine` | `npm install`, `npm test` |

Some tests in `interfaces/python` cross-check the models against the normative RoIS
machine-readable files, which are not redistributed in this repository. Those tests are
skipped or fail without them.

## Key Conventions

- Python 3.12+, Pydantic v2, `from __future__ import annotations`, PEP 695 `type`
  statements, mypy strict, ruff line length 100.
- TypeScript ESM, strict typecheck, vitest.
- C# `netstandard2.1` (Unity 6.5+), `sealed class`, `Nullable` enabled.
- `interfaces/python/src/` and `core/src/` stay transport-neutral and paradigm-neutral.
  No ROS, DDS, gRPC, or game engine imports. Those belong in components.
- Do not change the `Component Contract` (`discover`, `invoke`, `query`, `subscribe`,
  `unsubscribe`) without reading section 8 of [docs/architecture.md](docs/architecture.md).
  It is the contract that keeps the engine paradigm-neutral.
- Components own their backend connections, created in `connect()` and closed in
  `disconnect()`. Adapters never hold shared backend state.

## Writing Style

Applies to documentation, code comments, commit messages, and pull request
descriptions.

- **No em dashes** (`—`), **no en dashes** (`–`), **no double dashes** (`--`) as
  punctuation, and **no semicolons** in prose. Use colons, commas, parentheses, or
  separate sentences.
- **OpenRoIS** is the project and organization name, always with this capitalization.
  **openrois** is the URL slug and package scope, always lowercase. **OpenRoIS
  Community** is the author field in package metadata. **Coarobo GK** is the copyright
  holder in legal files. **OMG RoIS Framework 2.0** is the full specification name.
  **Apache-2.0** is the license identifier.
- **Title Case** for headings, buttons, navigation labels, badges, and card titles
  ("Get Started", "Project Status"). Sentence case for body text and table cells.
- Technical, precise, confident. No marketing language. State what the software does,
  not what it "empowers".
- Say "physical robots, virtual avatars, and AI services" (the paper says "physical
  robots and virtual agents"), not "robots" alone. Never "digital agents".
- Say "Alpha, pre-1.0, unstable API". Never claim production readiness before v1.0.
- Mark anything not implemented as "in progress" or "planned", in documentation and in
  code comments alike. Do not describe a target design as if it already works.
- Code comments are complete sentences that explain *why*, not *what*.

## Where to Look

| Topic | Document |
|-------|----------|
| Architecture and design rationale | [docs/architecture.md](docs/architecture.md) |
| Motivation, wire protocol, topologies | [docs/white-paper.md](docs/white-paper.md) |
| The RoIS specification, summarized | [docs/rois-reference.md](docs/rois-reference.md) |
| Phases, status, exit criteria | [docs/roadmap.md](docs/roadmap.md) |
| Contribution process | [CONTRIBUTING.md](CONTRIBUTING.md) |
