# AGENTS.md

> Guide for AI coding agents working in this repository. Read this first.

## What This Is

OpenRoIS is an open-source middleware implementing the OMG RoIS Framework
**Version 2.0-beta2**. The spec is beta and may change. Only the **interfaces**
layer (M0) exists. The engine, gateway, bus adapters, components, and SDKs are
planned but not built. See `docs/roadmap.md` for the milestone roadmap.

## The One Critical Rule

Types flow in one direction. **Never edit generated files by hand.**

```
Python (Pydantic) → JSON Schema → C# + TypeScript
```

- **Edit:** `interfaces/python/src/openrois/interfaces/*.py`
- **Don't edit:** `interfaces/schema/`, `interfaces/csharp/src/OpenRoIS.Interfaces/Generated/`, `interfaces/typescript/src/`

After editing Python models, run the full pipeline and all tests:

```bash
cd interfaces/python && python scripts/export_schema.py
cd ../typescript && npx tsx scripts/generate.ts && npm run typecheck && npm test
cd ../csharp && dotnet run --project scripts/Generator/Generator.csproj -- ../../schema && dotnet test
```

## Build and Test

| Stack | Dir | Commands |
|-------|-----|----------|
| Python (source) | `interfaces/python` | `pip install -e ".[dev]"`, `ruff check src/`, `mypy src/`, `pytest -q` |
| TypeScript (generated) | `interfaces/typescript` | `npm install`, `npm run generate`, `npm run typecheck`, `npm test` |
| C# (generated) | `interfaces/csharp` | `dotnet build`, `dotnet test` |

CI (`.github/workflows/ci.yml`) runs all three on changes to `interfaces/**`.

## Key Conventions

- Python 3.12+, Pydantic v2, `from __future__ import annotations`, PEP 695 `type` statements, mypy strict, ruff line-length 100
- TypeScript ESM, strict typecheck, vitest
- C# `netstandard2.1` (Unity 6.3+), `sealed class`, `Nullable` enabled
- `interfaces/python/src/` must stay transport-neutral. No ROS, DDS, gRPC, or WebSocket imports.
- Don't change the `BusAdapter` protocol without reading
  `docs/architecture.md` section 7.5.

## Writing Style

Applies to all documentation, code comments, commit messages, and PR descriptions.

- **No em-dashes** (`—`), **no en-dashes** (`–`), **no double dashes** (`--`) as punctuation, **no semicolons** in prose. Use colons, commas, parentheses, or separate sentences.
- **OpenRoIS**: project and org name (always this capitalization). **openrois**: URL slug and package scope (always lowercase). **OpenRoIS Community**: author field. **OMG RoIS Framework 2.0-beta2**: full spec name. **Apache-2.0**: license identifier.
- Technical, precise, confident. No marketing language. State what the thing does, not what it "empowers."
- Say "robots, avatars, and digital agents" (not "robots" alone). Say "Alpha, pre-1.0, unstable API" (not "production-ready" until v1.0).
- Code comments: complete sentences, explain *why* not *what*, no em-dashes or semicolons.

Architecture: `docs/architecture.md`. Spec reference: `docs/rois-reference.md`.
Roadmap: `docs/roadmap.md`. Style guide in the `openrois-internal` repo:
`branding.md`.
