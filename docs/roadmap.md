# OpenRoIS Roadmap

> What OpenRoIS has built and what comes next, for an open-source middleware implementing
> the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).
> [openrois.org](https://openrois.org/docs/project/roadmap) hosts the same roadmap.

Until `v1.0`, OpenRoIS is **alpha, pre-1.0, with an unstable API**. The milestones are in
order and carry no dates: each one is released when it is ready.

---

## 1. Milestones

This table is the status of record: the README, the white paper, the website and the
organization profiles copy it.

| Milestone | Status | What it delivers |
|-----------|--------|------------------|
| **`v0.1.0`** (November 2026) | ![Released](https://img.shields.io/badge/Released-2E7D32) | Every package at `0.1.0`, released together. A physical Reachy Mini and a simulated one behind one gateway, driven by one application and by an AI agent |
| **`v0.2`** | ![Planned](https://img.shields.io/badge/Planned-6E7781) | RoIS conformance: components declared by XML profiles at run time, the types checked against the normative RoIS files on every change, a test suite that adapter authors run against their own adapter, and a conformance claim. Applications and engines that recover when a gateway or an adapter restarts |
| **`v0.3`** | ![Planned](https://img.shields.io/badge/Planned-6E7781) | A physical robot and a digital avatar behind one gateway, controlled by one application that does not know which is which |
| **`v0.4`** | ![Planned](https://img.shields.io/badge/Planned-6E7781) | Authentication at the WebSocket upgrade and authorization per RoIS operation. Until then, a reverse proxy in front of the gateway terminates TLS ([SECURITY.md](../SECURITY.md)). An adapter for a second robot |
| **`v0.5`** | ![Planned](https://img.shields.io/badge/Planned-6E7781) | Media for the AudioStreaming and VideoStreaming components. OpenRoIS does not prescribe a media transport: a streaming component returns a descriptor of its stream, and an optional WebRTC integration serves deployments that have none |
| **`v1.0`** | ![Planned](https://img.shields.io/badge/Planned-6E7781) | A stable API, and the first release with semantic versioning guarantees. It stands on the milestones above: the conformance claim, authentication, and reference adapters for two robots and a digital avatar, on Linux, Windows and macOS |
| Beyond `v1.0` | ![Beyond 1.0](https://img.shields.io/badge/Beyond%201.0-8B98A8) | The remaining basic RoIS HRI Components, each released when it is ready. A registry of community components and adapters, and a Hub that shows operators the adapters, sessions and health of a deployment |

## 2. The Stack, Bottom Up

Each layer builds on the one below it.

| Layer | Packages | Role |
|-------|----------|------|
| **Interfaces** | `openrois-interfaces` (PyPI), `@openrois/interfaces` (npm), C# types inside the Unity package | The RoIS types and method catalog that every other layer speaks. Authored once in Python and generated through JSON Schema into TypeScript and C#, with all 18 normative profiles and an XML profile codec, cross-checked against the OMG machine-readable files |
| **Engine** | `openrois-engine` | One recursive engine for both the main and the sub HRI Engine roles. It carries the RoIS interfaces, profiles and common messages: sessions, binds, command sequences with concurrent branches, timeouts, events and the error channel, as [rois-reference §16](rois-reference.md#16-known-normative-divergences) records them. It serves and consumes RoIS over WebSocket, so a gateway can sit under a gateway, and grows to components declared by XML profiles at run time |
| **Engine processes** | `openrois-gateway`; the adapter process | The engine as deployable processes. The gateway is the main HRI Engine that applications connect to, configured by YAML, environment or flags and shipped as a container image with Docker Compose. An adapter process is a sub HRI Engine that hosts the components of one robot or agent, configured by `adapter.yaml` |
| **Components** | `openrois-components-core`; each robot's package in its adapter repository | The RoIS HRI Components themselves. The component SDK (`@component`, `@command`, `@query`, `@event`, resources, ROS 2 support) turns a capability of a robot or a digital avatar into a component, and the per-robot packages build on it toward the 17 basic components. The Reachy Mini adapter is the reference, run on the real robot and in simulation |
| **Client SDKs** | `@openrois/sdk` (npm), `openrois-sdk` (PyPI), `org.openrois.sdk` (Unity, by Git URL) | How service applications speak RoIS from JavaScript, Python and Unity, with typed models over the wire protocol and one conformance list that all three pass |
| **Applications** | `openrois-mcp`; the OpenRoIS Inspector | Ready-made service applications: an MCP server that lets AI agents drive the robots behind a gateway, and the OpenRoIS Inspector, which shows the engines and components behind a gateway and drives them as a service application does. A Hub for operators follows beyond `v1.0` |

## 3. Versioning

- The packages share their major and minor version and are released together under a
  project tag such as `v0.1.0`. A package may carry its own pre-release or patch number
  in between.
- `0.x` releases may break the API without notice.
- `v1.0` is the first release with semantic versioning guarantees.

## 4. Contributing

An adapter for a new robot, with its components in its own repository, is the natural
entry point. See [CONTRIBUTING.md](../CONTRIBUTING.md), or open an issue to propose a
change to the roadmap. All work is released under the [Apache-2.0](../LICENSE) license.
