# OpenRoIS Roadmap

> The public phase roadmap for OpenRoIS, an open-source middleware implementing the
> [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0). Each phase delivers a
> coherent capability with explicit exit criteria.
>
> Companion documents:
>
> - [architecture.md](architecture.md) is the engineering design document.
> - [white-paper.md](white-paper.md) is the R&D white paper.
> - [rois-reference.md](rois-reference.md) is the OMG specification summary.
> - [openrois.org](https://openrois.org/docs/project/roadmap) hosts the same roadmap
>   as part of the living documentation.

---

## 1. Overview

Until version 1.0, all releases are **alpha, with an unstable API**.

| Phase | Theme | Status |
|-------|-------|--------|
| **0** | Paradigm-neutral interface types | done |
| **1** | Engine and sub HRI Engine proof of concept | done |
| **2** | Adapter framework and reference components | done |
| **3** | Client SDKs and first end-to-end demonstration | in progress |
| **4** | Recursive core in Python | in progress |
| **5** | Hardening the core | planned |
| **6** | Gateway process | planned |
| **7** | Adapter process | planned |
| **8** | Open reference platform and mixed paradigms | planned |
| **9** | Authentication, security, and media | planned |
| **10** | Full component library (`v1.0`) | planned |
| **11** | Component registry and Hub | after 1.0 |

Phase 3 continues alongside Phase 4. Phases 8 and 9 can proceed in parallel once the
gateway and adapter processes exist. Phase 11 is gated on adoption.

---

## 2. Phase Details

### Phase 0: Paradigm-Neutral Interface Types (Done)

RoIS types authored as Python models, exported to JSON Schema, and generated into
TypeScript and C#, with tests against the normative RoIS files. Definition of the
five-method `Component Contract` that decouples the engine from any middleware.

### Phase 1: Engine and Sub HRI Engine Proof of Concept (Done)

A TypeScript engine that routes RoIS calls to sub HRI Engines over WebSocket, aggregates
their profiles, tracks reservations, and broadcasts profile changes. This proof of
concept lives in `gateway/` and is retired at the end of Phase 4.

### Phase 2: Adapter Framework and Reference Components (Done)

The decorator-based component framework (`@component`, `@query`, `@invoke`,
`@subscribe`), component-owned backend connections, and reference `Navigation` and
`SystemInformation` components for the Preferred Robotics Kachaka with gRPC and ROS 2
backends.

### Phase 3: Client SDKs and First End-to-End Demonstration (In Progress)

**Done:** the TypeScript SDK (`@openrois/sdk`), the profile-driven web client
(`examples/hri-client`), the mock engine (`examples/mock-engine`), and an end-to-end
demonstration of a web application controlling a physical robot through the gateway and
an adapter.

**In progress:** the C# client SDK for Unity. Its JSON-RPC layer exists, and the
high-level client does not yet.

**Exit criteria:** tagged release `v0.1.0`.

### Phase 4: Recursive Core in Python (In Progress)

**Done:** the `openrois-core` package with the recursive `Engine`, the
`ComponentRegistry`, the `SubEngine` proxy, and the `WsServer` and `WsClient` that
existing adapters run on.

**In progress:** reliability fixes for adapter discovery and event delivery in the
gateway, and a regression test suite for the core.

**Exit criteria:** one dispatch implementation, with the TypeScript proof of concept
retired.

### Phase 5: Hardening the Core (Planned)

Graceful shutdown, reconnection behavior, loading component packages from a local path
or a Git URL, and minimal health and status endpoints.

### Phase 6: Gateway Process (Planned)

A standalone gateway process and container image composed from `Engine` and `WsServer`,
with configuration loading, logging, signal handling, and one-command bring-up.

### Phase 7: Adapter Process (Planned)

A standalone adapter process composed from `Engine`, `WsClient`, and a backend bridge,
configured by the adapter profile.

### Phase 8: Open Reference Platform and Mixed Paradigms (Planned)

A reference platform based on the open-source Pollen Robotics Reachy Mini, shipped with
OpenRoIS so that anyone can run the full stack on affordable, openly documented hardware.
A demonstration of a physical robot and a virtual agent behind one gateway, controlled by
one application that does not know which is which.

Completing this phase starts the transfer of OpenRoIS to a neutral open-source
foundation.

### Phase 9: Authentication, Security, and Media (Planned)

JWT authentication at the WebSocket upgrade, role-based authorization per RoIS
operation, the RoIS Streaming Interface with WebRTC media, and DDS Security for ROS 2
based adapters.

### Phase 10: Full Component Library (Planned)

All 17 basic RoIS HRI Components, for physical robots and virtual avatars, and packages
published to PyPI, npm, NuGet, and the Unity Package Manager. First stable release with
semantic versioning guarantees: **`v1.0`**.

### Phase 11: Component Registry and Hub (After 1.0)

A registry of community components and adapters for additional platforms, and a Hub web
application that visualizes connected adapters, components, and their status.

---

## 3. Versioning

- `0.x` releases are pre-releases. Breaking changes may happen without notice.
- `v1.0` is the first release with semantic versioning guarantees.

---

## 4. Open Decisions

Recorded as architecture decision records when settled.

### Adapter Language (Decided)

Adapters stay in Python for ROS 2 ergonomics through `rclpy`. An adapter hosts an
`Engine` (a sub HRI Engine) with components registered in its `ComponentRegistry`, and
connects to the gateway with `WsClient`. The shared contract is the generated
`Component Contract`, not a shared codebase.

### Package Management Mechanism (Undecided)

The component registry of an adapter needs to load component packages from somewhere.
The proposal is to start with local paths and Git URLs, then add a registry endpoint
later as the foundation for Phase 11. Package management stays in the adapter and the
gateway management API, never in the `Engine`.

### Component Registry Implementations (Recommendation)

Two thin native implementations, one per language, sharing only the generated
`Component Contract`, rather than one shared library bridged across languages.

---

## 5. Contributing

Many items above can be picked up in parallel, and components for new robots are the
natural entry point. See [CONTRIBUTING.md](../CONTRIBUTING.md), or open an issue to
propose a change to the roadmap.

---

## 6. License

All phases are **Apache-2.0**. See the [LICENSE](../LICENSE) file.

---

*For the system design, see [architecture.md](architecture.md). For the OMG
specification summary, see [rois-reference.md](rois-reference.md). For authoritative
requirements, consult the OMG specification at <https://www.omg.org/spec/RoIS/2.0>.*
