# Contributing to OpenRoIS

> How to contribute code to OpenRoIS. Read this before your first PR. For AI
> coding agent guidance, see `AGENTS.md`. For the milestone roadmap, see
> `docs/roadmap.md`.

---

## Table of Contents

1. [Before You Start](#1-before-you-start)
2. [Code Style](#2-code-style)
3. [Testing](#3-testing)
4. [Changelog](#4-changelog)
5. [Package READMEs](#5-package-readmes)
6. [Conventional Commits](#6-conventional-commits)
7. [Conventional Branches](#7-conventional-branches)
8. [Conventional Comments](#8-conventional-comments)
9. [Additional Conventions](#9-additional-conventions)
10. [Git Workflow](#10-git-workflow)
11. [CI](#11-ci)

---

## 1. Before You Start

Read `AGENTS.md` in the repo root. It covers the critical rule about generated
files, build commands, and key conventions. The writing style rules in `AGENTS.md`
apply to all documentation, code comments, commit messages, and PR descriptions.

## 2. Code Style

### TypeScript

- **Strict mode**: no `any`, no implicit returns, no unchecked null access
- **ESM**: use `import`/`export`, not `require`
- **Naming**: `camelCase` for variables and functions, `PascalCase` for classes and
  types
- **TSDoc**: document every public class, method, and function with `/** ... */`
  comments

### Python

- Python 3.12+, Pydantic v2, `from __future__ import annotations`
- PEP 695 `type` statements, mypy strict, ruff line-length 100
- `interfaces/python/src/` must stay transport-neutral. No ROS, DDS, gRPC, or
  WebSocket imports.

### C\#

- `netstandard2.1` (Unity 6.3+), `sealed class`, `Nullable` enabled

## 3. Testing

- Use **vitest** for TypeScript tests, **pytest** for Python, **dotnet test** for C\#
- Write tests alongside implementation, not after
- Target **85%+ coverage** for new packages
- Test error paths, not just the happy path
- Name test files `*.test.ts` (TypeScript) or `test_*.py` (Python) in the `tests/`
  directory

## 4. Changelog

Every package has a `CHANGELOG.md` file. Update it when you make changes.

- Format: [Keep a Changelog](https://keepachangelog.com/en/2.0.0/)
- Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
- Add entries under `## [Unreleased]` as you work
- Move them to a versioned section when you tag a release
- Categories: `Added`, `Changed`, `Fixed`, `Removed`, `Deprecated`, `Security`

Example entry:

```markdown
## [Unreleased]

### Added

- WebSocket transport layer with browser and Node.js support.
- JSON-RPC 2.0 message types and framing.

### Fixed

- Race condition in request/response correlation when multiple requests are in flight.
```

## 5. Package READMEs

Every package has a `README.md`. Include:

- **One-line description** of what the package does
- **Installation** instructions
- **Quickstart**: a 5-minute guide that gets a user connected and receiving events
- **API overview**: the main classes and their methods
- **Error handling**: the error hierarchy and how to catch specific errors
- **Examples**: at least one complete working example
- **License**: Apache-2.0

## 6. Conventional Commits

Follow the [Conventional Commits](https://www.conventionalcommits.org/)
specification for all commit messages:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**

| Type | When to use |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only changes |
| `test` | Adding or correcting tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Code change that improves performance |
| `chore` | Build, tooling, dependencies, CI |
| `style` | Formatting, whitespace, semicolons (no code logic change) |

**Scope** (optional): the module or area affected (e.g., `transport`, `jsonrpc`,
`engine`, `demo`).

**Examples:**

```
feat(transport): add WebSocket transport with browser and Node.js support
fix(jsonrpc): handle missing id field in notifications
docs(readme): add quickstart guide and error handling section
test(events): add unsubscribe cleanup test
chore(ci): add sdk typescript workflow with vitest and coverage
```

**Rules:**
- Imperative mood: "add" not "added", "fix" not "fixed"
- Lowercase, no period at the end
- Description under 72 characters in the subject line
- Body explains *why*, not *what* (the diff shows what)
- Use `BREAKING CHANGE:` in the footer for breaking changes (rare at alpha stage)

## 7. Conventional Branches

Name branches with a type prefix, a scope, and a short description:

```
<type>/<scope>-<description>
```

| Prefix | Example |
|--------|---------|
| `feat/` | `feat/transport-layer` |
| `fix/` | `fix/jsonrpc-id-correlation` |
| `docs/` | `docs/readme-quickstart` |
| `test/` | `test/reconnect-backoff` |
| `chore/` | `chore/tsup-dual-build` |
| `refactor/` | `refactor/event-dispatch` |

**Rules:**
- Kebab-case (lowercase, hyphens)
- Keep branch names short but descriptive
- One branch per feature or fix
- Delete branches after merge

## 8. Conventional Comments

Use [Conventional Comments](https://conventionalcomments.org/) for all code review
feedback (both giving and receiving). Prefix each comment with a label:

| Label | Meaning | Example |
|-------|---------|---------|
| `praise:` | Highlight something positive | `praise: clean error hierarchy, easy to follow` |
| `nitpick:` | Trivial preference, not blocking | `nitpick: prefer const over let here` |
| `suggestion:` | Propose an improvement | `suggestion: extract this into a helper for reuse` |
| `issue:` | Something is wrong and should be fixed | `issue: this timer is never cleared on disconnect` |
| `question:` | Need clarification | `question: should this retry on TIMEOUT?` |
| `thought:` | An idea, not requiring action | `thought: we could use AbortController here later` |
| `polish:` | Non-blocking improvement | `polish: add TSDoc to this public method` |

**Rules:**
- Labels are lowercase, followed by a colon and a space
- `issue:` and `suggestion:` are the most common in review
- `nitpick:` and `polish:` are non-blocking: the author can accept or decline
- `praise:` is encouraged. Positive feedback is part of good review culture

## 9. Additional Conventions

These are conventions the team follows that are not yet formalized elsewhere.

### Error messages

- Write error messages as complete sentences: "WebSocket connection failed" not
  "ws error" or "failed"
- Include context: "WebSocket connection failed: gateway at ws://localhost:8765
  returned HTTP 401" not just "connection failed"
- Do not include stack traces in error messages (the runtime adds those)
- Error classes should carry structured data (e.g., `ReturnCodeError.returnCode`,
  `ReturnCodeError.method`), not just a string

### Import ordering (TypeScript)

Group imports in this order, separated by blank lines:

```typescript
// 1. Node.js built-ins
import { EventEmitter } from "node:events";

// 2. External packages
import { z } from "zod";
import type { WebSocket } from "ws";

// 3. Internal packages (@openrois/*)
import { ReturnCodeSchema } from "@openrois/interfaces";
import type { ReturnCode } from "@openrois/interfaces";

// 4. Local modules (relative)
import { Transport } from "./transport";
import { JsonRpcRequest } from "./jsonrpc";
```

Use `import type` for type-only imports. This helps bundlers tree-shake and makes
the intent clear.

### File naming

- Source files: `kebab-case.ts` (e.g., `system-client.ts`, `component-proxy.ts`)
- Test files: `kebab-case.test.ts` (e.g., `transport.test.ts`)
- Types and interfaces: defined in the module that owns them, not in a shared
  `types.ts` unless they are truly cross-cutting

### Export style

- Use named exports, not default exports. Named exports are refactor-safe and
  explicit.
- Re-export public API from `index.ts` only. Internal modules should not be
  imported directly by consumers.
- Group exports logically: core classes first, then errors, then types.

### Dependency management

- Pin major versions in `package.json` (e.g., `"ws": "^8.0"`, not `"ws": "*"`)
- Use `devDependencies` for test, build, and lint tools
- Use `dependencies` for runtime requirements only
- Do not add a dependency without checking it is actively maintained and
  Apache-2.0 compatible
- Run `npm audit` before tagging a release

### Code review etiquette

- Review within 24 hours of PR submission
- Be specific: reference line numbers or code snippets
- Distinguish blocking from non-blocking feedback using Conventional Comments labels
- Ask questions before making assumptions
- Approve only when you would be comfortable maintaining the code yourself
- Do not approve your own PRs

### PR descriptions

Use this template for every PR:

```markdown
## What

[1-2 sentences: what does this PR add or change?]

## Why

[1-2 sentences: why is this needed? Link to an issue or milestone if applicable.]

## How

[Brief description of the approach. Mention any design decisions worth noting.]

## Testing

- [ ] All tests pass (`npm test`)
- [ ] Type checking passes (`npm run typecheck`)
- [ ] Linting passes (`npm run lint`)
- [ ] New tests added for new functionality
- [ ] CHANGELOG.md updated
```

## 10. Git Workflow

### Branches

- Create a feature branch for each piece of work: `git checkout -b feat/transport-layer`
- Use prefixes: `feat/`, `fix/`, `docs/`, `test/`, `chore/`
- Keep branches short-lived (merge within a few days)

### Commits

- Write clear commit messages in the imperative mood: "Add WebSocket transport
  layer" not "Added WebSocket transport layer"
- Keep commits focused: one logical change per commit
- If a commit needs a long explanation, the code might need simplifying

### Pull requests

- Open a PR when a feature is ready for review (not when it is perfect, but when it
  is testable)
- Address review feedback in new commits (do not force-push during review)
- Squash-merge when approved

## 11. CI

- The CI pipeline (`.github/workflows/ci.yml`) runs on every push
- CI must be green before merge
- New packages should add their own workflow file (e.g.,
  `.github/workflows/sdk-typescript.yml`)