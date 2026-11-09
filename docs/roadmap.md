# OpenRoIS Roadmap

> What OpenRoIS has built and what comes next, layer by layer, for an open-source
> middleware implementing the [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0).
> [openrois.org](https://openrois.org/docs/project/roadmap) hosts the same roadmap.

Until `v1.0`, OpenRoIS is **alpha, pre-1.0, with an unstable API**.

---

## 1. The Stack, Bottom Up

Each layer builds on the one below it. The table is the status of record: the README,
`AGENTS.md`, the white paper, the website and the organization profile copy it.

| Layer | Packages | In `v0.1.0` | Next |
|-------|----------|-------------|------|
| **Interfaces** | `openrois-interfaces` (PyPI), `@openrois/interfaces` (npm), C# types inside the Unity package | The RoIS types and method catalog, authored in Python and generated through JSON Schema into TypeScript and C#. All 18 normative profiles and an XML profile codec, cross-checked against the OMG machine-readable files | The cross-check running in CI |
| **Engine** | `openrois-engine` | One recursive engine for the main and sub HRI Engine roles. The RoIS interfaces, profiles and common messages (CP1 to CP3) as [rois-reference §16](rois-reference.md#16-known-normative-divergences) records them: sessions, binds, full command sequences with concurrent branches, timeouts, events and the error channel. `WsServer` and `WsClient`, a gateway under a gateway | Components declared by XML profiles at run time (CP4). Sessions told when an engine stops, subscriptions restored after an adapter reconnects |
| **Engine processes** | `openrois-gateway`; the adapter process | The gateway process: YAML, environment and flag configuration, a container image, and Docker Compose with a mock adapter. Adapters configured by `adapter.yaml` | A packaged adapter process that needs no hand-written script. Health and status endpoints. Component packages loaded from a local path or a Git URL |
| **Components** | `openrois-components-core`, `openrois-components-common`; each robot's package in its adapter repository | The component SDK: `@component`, `@query`, `@invoke`, `@subscribe`, resources, the RoIS_Common default, ROS 2 support. SystemInformation. The Reachy Mini adapter with PersonDetection, Reaction, SpeechSynthesis and SystemInformation, run on the real robot and in simulation | Components for a virtual agent. More of the 17 basic components |
| **Client SDKs** | `@openrois/sdk` (npm), `openrois-sdk` (PyPI), `org.openrois.sdk` (Unity, by Git URL) | One conformance list passed by all three SDKs. The Unity SDK run in Linux players and the Editor | Unity on Windows, macOS, Android and VR headsets. Readable error reasons |
| **Applications** | `openrois-mcp`; the HRI client | An MCP server that lets AI agents drive the robots behind a gateway. A profile-driven web client | The HRI client as an application with command sequences. A Hub for operators, after `v1.0` |

## 2. Milestones

| Milestone | What it delivers |
|-----------|------------------|
| **`v0.1.0`** (November 2026) | Every package above at `0.1.0`, released together. A physical Reachy Mini and a simulated one behind one gateway, driven by one application and by an AI agent |
| **`v0.2`** | A physical robot and a virtual agent behind one gateway, controlled by one application that does not know which is which. Components declared by XML profiles at run time, and a RoIS conformance claim |
| **`v0.3`** | Authentication at the WebSocket upgrade and authorization per RoIS operation. Until then, a reverse proxy in front of the gateway terminates TLS ([SECURITY.md](../SECURITY.md)) |
| **`v0.4`** | Media for the AudioStreaming and VideoStreaming components. OpenRoIS does not prescribe a media transport: a streaming component returns a descriptor of its stream, and an optional WebRTC integration serves deployments that have none |
| **`v1.0`** | All 17 basic RoIS HRI Components, for physical robots and virtual agents. The first release with semantic versioning guarantees |
| After `v1.0` | A registry of community components and adapters, and a Hub that shows operators the adapters, sessions and health of a deployment |

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
