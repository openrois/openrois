# OpenRoIS Roadmap

> The public phase roadmap for the OpenRoIS open-source middleware, an
> implementation of the OMG RoIS Framework 2.0-beta2. Phases replace the old
> flat milestone list because the recursive-core migration does not fit a
> milestone numbered alongside features.
>
> Companion documents:
> - [architecture.md](architecture.md) is the engineering design document.
> - [rois-reference.md](rois-reference.md) is the OMG specification summary.
> - [white-paper.md](white-paper.md) is the R&D white paper.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Dependency Graph](#2-dependency-graph)
3. [Phase Details](#3-phase-details)
4. [Versioning](#4-versioning)
5. [What Changes vs the Old Roadmap](#5-what-changes-vs-the-old-roadmap)
6. [Open Decisions](#6-open-decisions)
7. [License](#7-license)

---

## 1. Overview

OpenRoIS is built in phases. Each phase delivers a coherent architectural shift
or a working end-to-end capability, not an isolated layer. Phases 0 through 3
are complete. They laid the groundwork: the type pipeline, the engine, the
adapter framework with reference components, and the client SDKs with the MVP
demonstration. The recursive core refactor (Phase 4) continues from there.

| Phase | Theme | Exit tag | Status |
|-------|-------|----------|--------|
| **0** | Paradigm-Neutral Interfaces | type pipeline, `Component Contract` | done |
| **1** | Engine and Sub-engine | TypeScript engine POC, `SubEngine` proxy, mock components | done |
| **2** | Adapter Framework and Components | Python `AdapterFramework`, reference components, real robot adapter | done |
| **3** | Client SDKs and MVP | `v0.1.0` | done |
| **4** | Recursive Core Refactor | one Engine class in Python `openrois_core`, eliminate duplicate dispatch | todo |
| **5** | Solidify the Core | harden engine, component framework, package management v0 | todo |
| **6** | Gateway Process | compose `Engine` + `WsServer` from `openrois_core` | todo |
| **7** | Adapter Process | compose `Engine` + `WsClient` from `openrois_core` + backend bridge | todo |
| **8** | Real Component and Mixed Paradigm | paradigm-neutrality proof | todo |
| **9** | Auth, Security, Media | parallelizable after Phase 7 | todo |
| **10** | Full Component Library | `v1.0` | todo |
| **11** | Hub and Component Marketplace | post-1.0, adoption-gated | parked |

A prototype demo sprint (D1) already produced prototype-quality code across
early phases for a partner integration. The public roadmap formalizes that work
into release-quality phases. The demo is a reference, not a release.

The **MVP is Phase 3**: the minimum that lets a service application clone, build,
and control a real robot from a web application over WebSocket. The
**paradigm-neutrality proof is Phase 8** (mixed robot and avatar on one gateway).
The **foundation migration trigger fires after Phase 8, before Phase 10**: the
paradigm-neutrality proof is the governance milestone that initiates migration to
a neutral foundation home. The **1.0 release is Phase 10**.

---

## 2. Dependency Graph

```
Phase 0 (Interfaces) -- done
  |
  v
Phase 1 (Engine and Sub-engine) -- done
  |
  v
Phase 2 (Adapter Framework and Components) -- done
  |
  v
Phase 3 (Client SDKs and MVP, v0.1.0) -- done
  |
  v
Phase 4 (Recursive Core Refactor)
  |
  v
Phase 5 (Solidify the Core)
  |
  v
Phase 6 (Gateway Process)
  |
  v
Phase 7 (Adapter Process)
  |
  +-> Phase 8 (Real Component, Mixed Paradigm)
  |     |
  |     +-> [foundation migration trigger]
  |           |
  |           v
  |     Phase 10 (Full Component Library, v1.0)
  |
  +-> Phase 9 (Auth, Security, Media)
        |
        v
      Phase 10 (Full Component Library, v1.0)

Phase 11 (Hub, Marketplace) -- parked, post-1.0, adoption-gated
```

- **Phase 0 to Phase 3** is the completed critical path to the MVP.
- **Phase 4 and Phase 5** refactor and solidify the recursive engine in Python
  `openrois_core`.
- **Phase 6 and Phase 7** compose the engine into the gateway and adapter
  processes. The gateway imports `Engine` and `WsServer` from `openrois_core`.
  The adapter imports `Engine` and `WsClient` from `openrois_core`. Both use the
  same `Engine` class. The difference is what is populated: the gateway has child
  engines, the adapter has local components.
- **Phase 8** adds a real component and proves the core is paradigm-neutral by
  running a robot and an avatar behind one gateway.
- **Phase 9** (auth, security, media) can proceed in parallel after Phase 7.
- **Phase 10** reuses the Phase 8 component pattern and is parallelizable across
  contributors. Streaming components depend on the media work in Phase 9.
- **Phase 11** is parked until the core is solid and has real adoption. It builds
  on the package management mechanism from Phase 5, not on a monolithic engine.

---

## 3. Phase Details

### Phase 0: Paradigm-Neutral Interfaces

**Theme:** Build the transport-independent type pipeline and the `Component Contract`
that decouples the engine from any specific middleware.

**Scope:**
- Author the RoIS interface types as Pydantic models in Python (source of truth).
- Export to JSON Schema (canonical wire contract).
- Generate TypeScript and C# types from the JSON Schema.
- Define the `Component Contract` interface: the five-method contract (`discover`,
  `invoke`, `query`, `subscribe`, `unsubscribe`) that decouples the engine from
  any specific middleware.

**Exit criteria:** The type pipeline produces consistent types across Python,
TypeScript, and C#. The `Component Contract` is defined and frozen.

**Status:** done

### Phase 1: Engine and Sub-engine

**Theme:** Build the TypeScript engine POC that routes RoIS calls and the
`SubEngine` proxy that connects sub-engines over WebSocket.

**Scope:**
- Implement the engine (`@openrois/engine`) in TypeScript as a proof of concept:
  WebSocket server, JSON-RPC 2.0 router, `SubEngine` proxy for child engines.
- Route the RoIS interfaces (`SystemIF`, `CommandIF`, `QueryIF`, `EventIF`,
  `StreamingIF`) from clients to sub-engines.
- Aggregate profiles from all connected sub-engines into one `HRI_Engine_Profile`
  returned by `get_profile()`.
- Broadcast `rois.system.profile_changed` when a sub-engine registers or
  disconnects.
- Add mock components for testing. The engine has zero references to ROS, DDS, or
  any game engine.

**Note:** This is a TypeScript POC. Phase 4 replaces it with a Python
`openrois_core` package using a single recursive `Engine` class.

**Exit criteria:** The engine routes RoIS calls to a `SubEngine` over
WebSocket. Mock components respond to `bind`, `execute`, `query`, and
`subscribe`. Profile aggregation and change broadcast work.

**Status:** done

### Phase 2: Adapter Framework and Components

**Theme:** Build the Python adapter framework and the reference components that
prove the sub-engine pattern works against a real robot.

**Scope:**
- Implement the Python `AdapterFramework` with decorators (`@component`,
  `@query`, `@invoke`, `@subscribe`), component registration, WebSocket client,
  reconnection with exponential backoff, and event emission.
- Implement component-owned connections: each component creates and manages its
  own backend connection in `connect()` and tears it down in `disconnect()`.
- Implement reference components: `Navigation` and `SystemInformation` with gRPC
  and ROS 2 backends, shipped as `openrois_components.kachaka`.
- Implement a user-defined non-canonical component (`NavigationInformation`) per
  RoIS spec section 12.
- Implement the reference adapter for a real robot (`openrois-adapter-kachaka`).
- Add mock adapter and adapter template for testing and onboarding.

**Exit criteria:** The adapter connects to the engine over WebSocket, registers
its components, and routes RoIS calls to component handlers. The reference
adapter controls a real robot via gRPC. Components own their connections.

**Status:** done

### Phase 3: Client SDKs and MVP

**Theme:** Ship the client SDKs and the MVP demonstration. Tag `v0.1.0`.

**Scope:**
- Ship `sdk/typescript` (`@openrois/sdk`): `RoISClient` with the five RoIS
  interfaces (System, Command, Query, Event, Streaming), WebSocket transport,
  auto-reconnect, profile-driven discovery.
- Ship `sdk/python` (`openrois-sdk`): client SDK for scripting and testing, plus
  the `AdapterFramework` for adapter authors.
- Ship `sdk/csharp` (`OpenRoIS.Sdk`): client SDK for Unity service applications.
- Ship the MVP service application (`examples/hri-client/`): a web application
  that connects to the gateway, fetches the profile, and renders a dynamic UI
  for every discovered component. Profile-driven, no hardcoded component names.
- Ship the mock engine and mock adapter for testing.
- Tag `v0.1.0`.

**Exit criteria:** From a clean checkout, a service application connects to the
gateway, discovers components, binds, executes commands, queries status, and
subscribes to events. The TypeScript, Python, and C# SDKs pass their test suites.
The release is tagged `v0.1.0`.

**Status:** done

### Phase 4: Recursive Core Refactor

**Theme:** Migrate from the TypeScript POC engine to a Python `openrois_core`
package with a single recursive `Engine` class. Eliminate the duplicate RoIS
JSON-RPC dispatch logic that exists today in both the TypeScript
`@openrois/engine` and the Python `AdapterFramework`.

**Scope:**
- Create the `openrois_core` Python package: `engine.py` (recursive `Engine`
  class), `component_contract.py` (the five-method interface),
  `component_registry.py` (decorator scanning, handler dispatch, lifecycle),
  `sub_engine.py` (remote child engine proxy over WebSocket), `ws_server.py`
  (gateway WebSocket server), `ws_client.py` (adapter WebSocket client).
- The `Engine` class is recursive: it has a `ComponentRegistry` (for local
  components) and a sub-engine registry (for child engines). When acting as the
  main engine (gateway), the `ComponentRegistry` is empty. When acting as a
  sub-engine (adapter), the sub-engine registry is empty. One class, one
  dispatch implementation.
- Rename `SubEngine` interface to `Component Contract` in `interfaces/`. Generate
  to both Python and TypeScript. Both sides depend on the generated contract.
- Migrate the existing Python `AdapterFramework` dispatch logic into the
  `Engine` class. The adapter becomes `Engine` + `WsClient` + backend bridge.
- Port the TypeScript engine tests to Python. The Python engine must pass the
  same tests as the TypeScript POC before the POC is retired.
- Verify the existing MVP still works end to end after the refactor.

**Exit criteria:** One dispatch implementation (Python `Engine` in
`openrois_core`). The TypeScript POC is retired. The `Component Contract` is
 generated from `interfaces/`. The MVP demo passes.

**Status:** todo

### Phase 5: Solidify the Core

**Theme:** Harden the recursive engine and the component framework. Introduce
package management v0. This phase solidifies the `openrois_core` library, not the
processes. The gateway and adapter processes are built in Phase 6 and Phase 7.

**Scope:**
- Harden `Engine`: RoIS method dispatch, bind/release tracking, event
  subscription routing, profile aggregation from local components and child
  engines. Add graceful shutdown hooks.
- Harden `ComponentRegistry`: component registration, decorator dispatch,
  component lifecycle (`connect`/`disconnect`), partial-spec profiles, multiple
  backends via separate classes.
- Harden `WsServer`: WebSocket server, JSON-RPC framing, role-based connection
  routing. Add reconnection handling for sub-engines.
- Harden `WsClient`: WebSocket client, reconnection with exponential backoff,
  JSON-RPC framing.
- Formalize the component framework: `@component`, `@query`, `@invoke`,
  `@subscribe` decorators, per-component config, component-owned connections.
- Add package management v0: the `ComponentRegistry` loads component packages
  from a configured source (local path or git URL). A minimal `Api` exposes
  management endpoints: list installed packages, enable/disable a package for a
  fleet, health-check. Dependency setup (Python venv, ROS 2 workspace, model
  weights) is the adapter's job, not the engine's.
- Add a minimal `Api` for operational endpoints (`GET /health`,
  `GET /agents`). This is the foundation for the management surface, not a full
  fleet management API yet.

**Exit criteria:** The `openrois_core` library is hardened, tested in isolation,
and documented. Component packages load from local path or git URL. The `Api`
serves health and fleet status. The MVP demo passes on the refactored core.

**Status:** todo

### Phase 6: Gateway Process

**Theme:** Compose the `openrois_core` engine into the gateway process. The
gateway imports `Engine` and `WsServer` from `openrois_core` and wires them into
a single process that faces the network.

**Scope:**
- Create the gateway process: import `Engine` and `WsServer` from
  `openrois_core`. Wire the WebSocket server to feed messages into the engine.
  The engine has child engines (sub-engines connected over WebSocket), no local
  components.
- Import the `Api` from `openrois_core`. Wire the REST endpoints to the engine
  and the package management surface.
- Add process-level concerns: configuration loading, logging, signal handling,
  graceful shutdown, health checks.
- Add Docker Compose support for one-command bring-up.
- Verify the gateway accepts both adapter connections (`rois.adapter.register`)
  and client connections (`rois.system.*`) on the same WebSocket port.

**Exit criteria:** The gateway process runs as a standalone binary or Docker
container. It routes RoIS calls from clients to connected sub-engines. The `Api`
serves health and fleet status. The MVP demo passes through the gateway
process.

**Status:** todo

### Phase 7: Adapter Process

**Theme:** Compose the `openrois_core` engine into the adapter process. The
adapter imports `Engine` and `WsClient` from `openrois_core` and wires them into a
single process that hosts components and connects to the gateway.

**Scope:**
- Create the adapter process: import `Engine` and `WsClient` from
  `openrois_core`. Wire the WebSocket client to connect to the gateway and register
  components. The engine has local components (registered via
  `ComponentRegistry`), no child engines.
- Add the backend bridge: the adapter loads a backend (rclpy, gRPC, IPC) based
  on its profile YAML. The backend bridge is the adapter's concern, not the
  engine's.
- Add process-level concerns: configuration loading (profile YAML), logging,
  signal handling, graceful shutdown, reconnection to the gateway.
- Wire the package loader: the `ComponentRegistry` imports component packages
  from the configured source (local path or git URL) and instantiates them.
- Verify the adapter connects to the gateway, registers its components, and
  routes RoIS calls to component handlers.

**Exit criteria:** The adapter process runs as a standalone script or Docker
container. It connects to the gateway, registers its components, and routes RoIS
calls to component handlers. The reference adapter controls a real robot via
gRPC. The MVP demo passes through the gateway and adapter processes.

**Status:** todo

### Phase 8: Real Component and Mixed Paradigm

**Theme:** Prove the core is paradigm-neutral by running a robot and an avatar
behind one gateway. This is the paradigm-neutrality proof and the foundation
migration trigger.

**Scope:**
- Replace one mock component with a real perception component (e.g., YOLO
  `PersonDetection`).
- Add a second adapter for a different paradigm (e.g., an avatar sub-engine).
- Prove one gateway serves both adapters simultaneously, behind the same SDK
  endpoint. The service application discovers and controls components from both
  paradigms without knowing which is which.
- Document the mixed-paradigm topology as a reference deployment.

**Exit criteria:** One gateway, two adapters (robot and avatar), one service
application controlling both. The paradigm-neutrality proof is documented and
reproducible.

**Status:** todo

### Phase 9: Auth, Security, Media

**Theme:** Add authentication, authorization, and WebRTC media. Parallelizable
after Phase 7.

**Scope:**
- Add `Auth` unit to the gateway: JWT verification at WebSocket upgrade, RBAC
  enforcement per RoIS operation (admin, operator, viewer, maintenance), fleet
  scoping at `search()`/`bind()`/`execute()`/`query()`/`subscribe()`.
- Add `Signaling` unit to the gateway: WebRTC descriptor brokering via the RoIS
  streaming interface (`connect_stream`, `suspend_stream`, `resume_stream`,
  `disconnect_stream`, `notify_stream_status`).
- Implement streaming components (`AudioStreaming`, `VideoStreaming`) with
  WebRTC media. P2P for small fleets, SFU for scale.
- Add DDS-Security or per-fleet DDS domains for ROS 2 sub-engines.

**Exit criteria:** Authentication and RBAC are enforced. WebRTC media flows
between a robot and a service application via the streaming interface. Streaming
components emit `notify_stream_status` events.

**Status:** todo

### Phase 10: Full Component Library

**Theme:** Implement all 17 basic RoIS components across both paradigms (robot
and avatar). Tag `v1.0`.

**Scope:**
- Implement all 17 basic components: PersonDetection, PersonLocalization,
  PersonIdentification, FaceDetection, FaceLocalization, SoundDetection,
  SoundLocalization, SpeechRecognition, GestureRecognition, SpeechSynthesis,
  Reaction, Navigation, Follow, Move, AudioStreaming, VideoStreaming,
  SystemInformation.
- Shared components (perception, speech) run the same ML models across
  paradigms. Paradigm-specific components (Navigation, Move, Follow, Reaction)
  have per-backend implementations.
- Streaming components depend on the media work from Phase 9.
- Tag `v1.0`. Publish release notes. First stable release with semantic
  versioning guarantees.

**Exit criteria:** All 17 basic components are implemented, tested, and
documented. The release is tagged `v1.0`.

**Status:** todo

### Phase 11: Hub and Component Marketplace

**Theme:** Build the management web app and the component registry on top of the
gateway `Api` unit. Post-1.0, adoption-gated.

**Scope:**
- Mature `apps/hub/` into a management web app that connects to the gateway `Api`
  over WebSocket and REST. Visualize sub-engines, components, status, fleet
  health.
- Add a component marketplace: a registry of certified components. Component
  vendors publish to the registry. Adapters deploy packages through the gateway
  `Api` or directly. The marketplace is a different source for the adapter's
  package loader and a different backend for the gateway `Api`, not new engine
  logic.
- A richer commercial Hub (audit trail, OTA, compliance) can be built on top of
  the open gateway `Api`.

**Exit criteria:** The Hub visualizes a live gateway. The marketplace accepts
component submissions and serves them to adapters. Adoption is sufficient to
sustain the marketplace.

**Status:** parked

---

## 4. Versioning

- `v0.1.0` (Phase 3): first pre-release. MVP demonstration. Unstable API,
  breaking changes may occur without notice.
- `v0.x` (Phases 4 to 9): incremental pre-releases. Unstable API.
- `v1.0` (Phase 10): first stable release with semantic versioning guarantees.
  All 17 basic components implemented across both paradigms.
- Phase 11: post-1.0. No version tag until the Hub and marketplace are feature
  complete and adoption-gated.

Pre-1.0 releases are Alpha, unstable API. Do not use in production until v1.0.

---

## 5. What Changes vs the Old Roadmap

| Old roadmap (M0-M11) | New roadmap (phases) | Why |
|----------------------|----------------------|-----|
| Flat milestone list (M0 to M11) | Phase structure (Phase 0 to Phase 11) | The recursive-core migration does not fit a milestone numbered alongside features. Phases separate architectural shifts from feature work. |
| M0 to M5 marked "done" | Phase 0 to Phase 3 marked "done" | The groundwork (interfaces, engine, adapter framework, components, SDKs, MVP) is preserved as completed phases. The work is not discarded. |
| Engine language: TypeScript POC | Engine language: Python `openrois_core` (Phase 4) | The TypeScript engine proved the architecture. Python unifies the control plane, adapter, and components in one language. No FFI, no language boundary. |
| "Two modes" model: engine runs in main mode (gateway) and sub mode (adapter) | Recursive engine: one `Engine` class, used by both gateway and adapter | The "two modes" model created a duplicate dispatch implementation in two languages. The recursive model uses one class. The difference is what is populated: the gateway has child engines, the adapter has local components. Phase 4 refactors this. |
| No process composition phases | Phase 6 (Gateway Process) and Phase 7 (Adapter Process) | The gateway and adapter are processes that import the `Engine` from `openrois_core` and compose it with `WsServer` or `WsClient`. Both use the same `Engine` class. |
| No package management | Package management v0 in Phase 5 | Package management is a process feature of the `Api` (gateway) and the `ComponentRegistry` loader (adapter), not engine logic. |
| Hub and marketplace not mentioned | Phase 11 (parked, post-1.0, adoption-gated) | The Hub and marketplace are long-term goals that build on the package management mechanism. They are parked until the core is solid and has real adoption. |
| Foundation migration not mentioned | Foundation migration trigger after Phase 8, before Phase 10 | The paradigm-neutrality proof (Phase 8) is the governance milestone that initiates migration to a neutral foundation home. |
| D1 demo sprint not mentioned | D1 referenced as context | A prototype demo sprint already produced code across early phases for a partner integration. The public roadmap formalizes that work. The demo is a reference, not a release. |

---

## 6. Open Decisions

Record these as ADRs (Architecture Decision Records).

### ADR-1: Adapter language (decided)

**Decision:** Keep adapters in Python for ROS 2 ergonomics (`rclpy`).

**Context:** The adapter needs to talk to ROS 2 nodes, gRPC servers, and other
Python-friendly backends. Python is the natural choice for the ROS 2 ecosystem.

**Consequence:** The Python adapter hosts an `Engine` (a sub-engine) with local
components registered via `ComponentRegistry`. It connects to the gateway via
`WsClient` and registers with the parent engine. The adapter IS an engine, not a
separate kind of process. The shared contract is the generated
`Component Contract` from `interfaces/`, not a shared codebase.

### ADR-2: Package management mechanism (undecided)

**Decision:** Undecided. Propose starting with local-path and git-URL sources and
a minimal REST `Api`.

**Context:** The adapter `ComponentRegistry` needs to load component packages
from somewhere. The gateway `Api` needs to expose management endpoints. The exact
mechanism (local path, git URL, registry endpoint, pip install) is not yet
decided.

**Proposal:** Start with local-path and git-URL sources in the adapter
`ComponentRegistry` loader. Add a minimal REST `Api` to the gateway for health
and fleet status. Expand to a registry endpoint later, as the foundation for the
component marketplace (Phase 11).

**Consequence:** Package management lives in the `Api` (gateway) and the
`ComponentRegistry` loader (adapter), never in the `Engine`. The engine stays
pure.

### ADR-3: ComponentRegistry shared across languages or two thin implementations (recommend two)

**Decision:** Recommend two thin native implementations sharing only the
generated `Component Contract`.

**Context:** The `ComponentRegistry` could be a shared library (e.g., a Python
package that both TypeScript and Python adapters import) or two thin native
implementations (one in TypeScript, one in Python) that share only the generated
contract.

**Recommendation:** Two thin native implementations. The TypeScript
`ComponentRegistry` is for future TypeScript adapters (e.g., an avatar
sub-engine in Node.js). The Python `ComponentRegistry` is for ROS 2 and gRPC
adapters. Both share the generated `Component Contract` from `interfaces/`. No
shared codebase, no language bridge, no FFI.

**Consequence:** Each language has a small, idiomatic `ComponentRegistry`. The
contract is the source of truth, not a shared implementation. Adding a new
adapter language (e.g., C# for Unity) means writing a thin `ComponentRegistry`
in that language and generating the contract from `interfaces/`.

---

## 7. License

All phases are **Apache-2.0**. See the `LICENSE` file in each package.

---

*For the system design, see [architecture.md](architecture.md). For the
OMG specification summary, see [rois-reference.md](rois-reference.md). For
authoritative requirements, consult the OMG specification at
<https://www.omg.org/spec/RoIS/2.0/Beta2>.*