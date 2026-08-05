# OpenRoIS Roadmap

> The public milestone roadmap for the OpenRoIS open-source middleware.

---

## Overview

OpenRoIS is built in vertical slices. Each milestone delivers a working
end-to-end path, not an isolated layer. The critical path (M0 to M5) culminates
in a web operator application controlling a ROS 2 robot over WebSocket.

| Milestone | Theme | Output | Status |
|-----------|-------|--------|--------|
| **M0** | Paradigm-Neutral Interfaces | `interfaces` (Pydantic to JSON Schema to C#/TS), `BusAdapter` contract | done |
| **M1** | Engine and Bus | `engine`, `UniversalBusAdapter`, mock components | todo |
| **M2** | Remote Gateway | `gateway` (WebSocket, JSON-RPC 2.0, auth hook) | todo |
| **M3** | ROS 2 Bus Adapter | `ROS2BusAdapter` (rclpy), no core changes | todo |
| **M4** | Mock ROS 2 Robot Components | `person_detection`, `navigation`, `system_information` nodes | todo |
| **M5** | Web SDK and Robot MVP | `sdk/typescript`, web operator app, **v0.1.0 release** | todo |
| **M8** | Real Robot Component and Mixed Paradigm | YOLO `person_detection`, robot + avatar on one gateway | todo |
| **M9** | Auth and Bus Security | `auth`, `rbac`, per-fleet isolation | todo |
| **M10** | WebRTC Media | Streaming components, telepresence | todo |
| **M11** | Full Component Library | All 17 basic components, both paradigms, **v1.0** | todo |

The **MVP is M5**: the minimum that lets an operator clone, build, and control a
ROS 2 robot from a web application over WebSocket. The **paradigm-neutrality
proof is M8** (mixed robot + avatar on one gateway). The **1.0 release is M11**.

---

## Dependency Graph

```
M0 -> M1 -> M2 -> M3 -> M4 -> M5 (Web SDK and Robot MVP, v0.1.0)
                                  |
                                  +- M8 (Mixed-paradigm proof)
                                  +- M9 (Auth/Security)
                                  +- M10 (Media) -> M11 (Full library, v1.0)
```

- **M0 to M5** is the critical path to the MVP.
- **M8** adds a real perception component and proves the core is paradigm-neutral
  by running a robot and an avatar behind one gateway.
- **M9** (auth/security) and **M10** (media) can proceed in parallel after M5.
- **M11** reuses the M4/M8 component pattern and is highly parallelizable across
  contributors. Streaming components depend on M10.

---

## Milestone Details

### M0: Paradigm-Neutral Interfaces (done)

Transport-independent type definitions derived from the OMG RoIS Framework 2.0
IDL. Authored as Pydantic models in Python, exported to JSON Schema (the canonical
wire contract), and generated into C# and TypeScript. Includes the `BusAdapter`
protocol: the four-method contract (`discover`, `invoke`, `query`, `subscribe`)
that decouples the engine from any specific middleware.

### M1: Engine and Bus

A bus-independent engine running the RoIS interfaces (`SystemIF`, `CommandIF`,
`QueryIF`, `EventIF`) against the `UniversalBusAdapter` with mock components. The
engine has zero references to ROS, DDS, or any game engine.

### M2: Remote Gateway

Expose the engine to remote clients over WebSocket with JSON-RPC 2.0 and a basic
JWT auth hook. One-command bring-up via Docker Compose.

### M3: ROS 2 Bus Adapter

Add the robot bus as a new `BusAdapter` over `rclpy`, without changing the engine
or gateway. RoIS operations map to ROS 2 primitives: synchronous to service,
long-running to action, async push to topic.

### M4: Mock ROS 2 Robot Components

A mock ROS 2 robot (sub-engine + component nodes) that the `ROS2BusAdapter`
discovers and controls. Includes `person_detection`, `navigation` (as a ROS 2
action), and `system_information` (as a ROS 2 service). No hardware or heavy ML
required.

### M5: Web SDK and Robot MVP

A TypeScript SDK for web applications plus a web operator app that controls the
mock ROS 2 robot over WebSocket. This is the MVP demo, tagged as `v0.1.0`. From a
clean checkout, an operator can bring up the gateway + mock robot and control it
from the browser.

### M8: Real Robot Component and Mixed Paradigm

Replace one mock with a real YOLO `person_detection` pipeline. Add a
mixed-paradigm test proving one gateway serves a robot (ROS 2) and an avatar
(in-process) at the same time, behind the same SDK endpoint.

### M9: Auth, Authorization and Bus Security

Multi-tenant segmentation enforced per RoIS operation. JWT/OIDC authentication,
RBAC authorization (admin, operator, viewer, maintenance), fleet scoping at
`search()`/`bind()`/`execute()`/`query()`/`subscribe()`, and bus-level isolation
via per-fleet DDS domains or DDS-Security.

### M10: WebRTC Media and Telepresence

Live audio/video for both telepresence (robot camera/mic) and rendered avatars,
controlled via the RoIS streaming interface. WebRTC signaling travels over the
existing WebSocket connection. P2P for small fleets, SFU for scale.

### M11: Full Component Library

All 17 basic RoIS components implemented across both paradigms (robot and avatar).
Shared components (perception, speech) run the same ML models. Paradigm-specific
components (navigation, move, reaction) have per-backend implementations. This
milestone is the **v1.0 release**.

---

## Versioning

- `v0.x`: unstable, breaking changes may occur without notice
- `v1.0` (M11): first stable release with semantic versioning guarantees

---

## License

All canonical milestones are **Apache-2.0**. See the `LICENSE` file in each
package.

---

*For the system design, see [architecture.md](architecture.md) in the internal
repository. For the OMG specification summary, see
[rois-reference.md](rois-reference.md) in the internal
repository.*