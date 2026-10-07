<p align="center">
  <a href="https://openrois.org/">
    <img src="docs/assets/openrois-logo.svg" alt="OpenRoIS logo" width="104" height="104">
  </a>
</p>

<h1 align="center">OpenRoIS</h1>

<p align="center">
  <strong>Open-source middleware implementing the OMG Robotic Interaction Service (RoIS) Framework 2.0</strong><br>
  Write a service application once. Run it on physical robots, virtual avatars, and AI services.
</p>

<p align="center">
  <a href="https://www.omg.org/spec/RoIS/2.0"><img src="https://img.shields.io/badge/OMG%20RoIS-2.0-0070C0" alt="OMG RoIS 2.0"></a>
  <a href="https://arxiv.org/abs/2609.21178"><img src="https://img.shields.io/badge/paper-arXiv%3A2609.21178-B31B1B?logo=arxiv&logoColor=white" alt="Paper on arXiv: 2609.21178"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2E5C8A" alt="License: Apache-2.0"></a>
  <a href="#project-status"><img src="https://img.shields.io/badge/status-alpha-A6821A" alt="Status: alpha"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/TypeScript-5.4+-3178C6?logo=typescript&logoColor=white" alt="TypeScript 5.4+">
  <img src="https://img.shields.io/badge/.NET%20Standard-2.1-512BD4?logo=dotnet&logoColor=white" alt=".NET Standard 2.1">
  <img src="https://img.shields.io/badge/ROS%202-Jazzy-22314E?logo=ros&logoColor=white" alt="ROS 2 Jazzy">
</p>

<p align="center">
  <a href="https://openrois.org/">Website</a> ·
  <a href="https://github.com/openrois">OpenRoIS GitHub Organization</a> ·
  <a href="https://arxiv.org/abs/2609.21178">OpenRoIS arXiv Preprint</a> ·
  <a href="https://www.omg.org/spec/RoIS/2.0">OMG RoIS Specification</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="docs/white-paper.md">White Paper</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/roadmap.md">Roadmap</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Overview

Service applications for human-robot interaction are usually written against the
hardware-specific interface of one platform, so a change of hardware forces a rewrite
of the application. The [OMG RoIS Framework 2.0](https://www.omg.org/spec/RoIS/2.0)
addresses this fragmentation with a platform-independent model: applications talk to
HRI Engines through five standard interfaces and exchange symbolic messages such as
"a person was detected" or "navigate to the kitchen", never raw sensor data or motor
commands.

A specification alone does not provide the maintained implementation, SDKs, and
adapters that adoption requires. **OpenRoIS is an openly developed implementation of
RoIS 2.0** that carries the standard from specification to practice, for physical
robots and virtual agents alike.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/openrois-concept-dark.svg">
    <img src="docs/assets/openrois-concept.svg" alt="Without a standard interface, N applications and M platforms need N times M integrations. With OpenRoIS, they need N plus M." width="860">
  </picture>
</p>

## Key Features

- **Recursive engine.** A single `Engine` class realizes both the main and the sub HRI
  Engine roles defined by RoIS. The gateway and every adapter share one dispatch
  implementation.
- **One component contract.** The engine reaches every component through one
  interface, whether the component runs in its own process or behind a child engine.
  ROS 2, gRPC, game engines, and cloud APIs stay inside components, so adding a paradigm
  never touches the core.
- **JSON-RPC 2.0 over WebSocket.** Every operation of the five RoIS interfaces maps to
  a namespaced method (`rois.system.*`, `rois.command.*`, `rois.query.*`,
  `rois.event.*`, `rois.stream.*`). The control plane works from browsers and across
  the internet. The Streaming Interface is planned.
- **Single source of truth for types.** RoIS types are authored once as Python
  Pydantic models, exported to JSON Schema, and generated into TypeScript and C#.
  Tests check the models against the normative RoIS XML profiles and schema.
- **Profile-driven applications.** Clients discover components, queries, commands, and
  events from the engine profile at runtime, so one application works with any robot
  behind the gateway.
- **Decorator-based components.** Adapter authors declare a component with
  `@component`, `@query`, `@invoke`, and `@subscribe`, and write only the code that
  talks to their robot.

## Architecture

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/openrois-architecture-dark.svg">
    <img src="docs/assets/openrois-architecture.svg" alt="OpenRoIS architecture: service applications use an SDK to reach the gateway, which hosts the main HRI Engine and forwards calls over JSON-RPC to adapters hosting sub HRI Engines for robots, avatars, and services." width="860">
  </picture>
</p>

| RoIS concept | OpenRoIS realization |
|--------------|----------------------|
| Service Application | Your application, built with the TypeScript or C# SDK |
| Main HRI Engine | The gateway process: `Engine` with child engines, behind a WebSocket server |
| Sub HRI Engine | An adapter process: `Engine` with local components, connected to the gateway |
| HRI Component | A class decorated with `@component`, hosted by an adapter |
| RoIS interfaces | JSON-RPC 2.0 methods in the `rois.*` namespaces |

Read the [white paper](docs/white-paper.md) for the design rationale and the full wire
protocol, and the [architecture document](docs/architecture.md) for implementation
details.

## Quickstart

Run a gateway with a simulated robot behind it, and inspect it from the browser. You need
[Docker](https://docs.docker.com/get-started/get-docker/) with Compose, and
[Node.js](https://nodejs.org/) 22 or later for the web inspector.

```bash
git clone https://github.com/openrois/openrois.git
cd openrois

# Terminal 1: the gateway on ws://127.0.0.1:8765, with the mock adapter behind it.
docker compose up --build
```

```bash
# Terminal 2: build the types and the SDK, start the web inspector, then open
# http://localhost:5173 and click Connect.
(cd interfaces/typescript && npm install && npm run build)
(cd sdk/typescript && npm install && npm run build)
cd examples/hri-client && npm install && npm run dev
```

The inspector reads the engine profile and renders every component it finds, with its
queries, parameters, commands, and events: `mock/navigation`, `mock/person_detection`
and `mock/system_information`, served by the mock adapter, an engine of its own below the
gateway. Nothing in the client is specific to the components on the other side.
`python gateway/scripts/smoke.py` checks the same stack from the command line.

To develop a client without Docker, the [mock engine](examples/mock-engine/README.md)
serves the same components from one Node.js process:
`cd examples/mock-engine && npm install && npm start`.

<p align="center">
  <img src="docs/assets/hri-client-demo.gif" alt="Screen recording of the OpenRoIS HRI Client connecting to the mock engine, querying components, binding, subscribing to events, and executing a command." width="760">
</p>

<p align="center"><sub>Recorded from this quickstart, with no robot attached. A <a href="https://openrois.org/#see-it-run">higher-resolution version</a> is on the website.</sub></p>

## Usage

### Write a Service Application

The TypeScript SDK exposes the RoIS interfaces with typed responses and runtime
validation.

```ts
import { RoISClient, componentRef, componentType } from "@openrois/sdk";

const client = await RoISClient.connect("ws://localhost:8765");

// Find a navigation component on any connected robot, then select it by ref.
const [nav] = await client.search(componentType({ authority: "OMG", code: "Navigation" }));
const target = componentRef(nav);

// Query state synchronously.
const status = await client.query("component_status", target);

// Subscribe to events.
client.on("reached_target", (event) => console.log(event.results));
await client.subscribe("reached_target", target);

// Reserve an actuation component, command it, then release it.
await client.bind(nav);
await client.setParameter(nav, [
  { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' },
]);
await client.execute([{ component_ref: nav, command_type: "start" }]);
await client.release(nav);

await client.disconnect();
```

### Write a Component for Your Robot

A component translates RoIS operations into calls to your platform, whether that is a
ROS 2 action, a gRPC service, or an HTTP API. The adapter hosts it in a sub HRI Engine
and connects it to the gateway.

```python
from openrois.components.core import Component, component, invoke, subscribe
from openrois.interfaces.components import NAVIGATION_PROFILE


@component(NAVIGATION_PROFILE)
class Navigation(Component):
    def __init__(self, robot_url: str) -> None:
        self._robot_url = robot_url

    async def connect(self) -> None:
        self._robot = await MyRobotClient.open(self._robot_url)

    @invoke("start")
    async def start(self) -> None:
        target = self.parameters["target_positions"][0]
        await self._robot.go_to(target)  # the command runs until the robot arrives
        self.emit("reached_target", target=target, is_final_target=True)

    @subscribe("reached_target")
    async def reached_target(self) -> None:
        pass  # start emits the event when the robot arrives.
```

The engine stores the parameters, answers `component_status`, and reports the end of each
command with `rois.command.completed`. Host the component in an engine and connect it to
the gateway:

```python
from openrois.engine import Engine, WsClient

engine = Engine("robot_1")
engine.add_component("navigation", Navigation("http://192.168.0.10:8080"))
WsClient(engine, "ws://gateway.example.com:8765").run()
```

Clients see the component as `robot_1/navigation`.

See [`examples/adapter-template`](examples/adapter-template) for a complete starting
point and [`components/kachaka`](components/kachaka) for reference components backed by
both gRPC and ROS 2.

## Project Status

OpenRoIS is **alpha, pre-1.0, with an unstable API**. The foundations are in place and
demonstrated with a physical robot. The rest of the RoIS surface is being built in the
open.

| Area | Status |
|------|--------|
| RoIS interface types (Python, JSON Schema, TypeScript, C#) | Available |
| Recursive engine, WebSocket server and client, and adapter SDK (Python) | Available, hardening |
| Gateway process, container image, and Docker Compose with a mock adapter | Available |
| TypeScript client SDK and web inspector | Available |
| Reference components for the Preferred Robotics Kachaka (gRPC and ROS 2) | Available |
| C# client SDK for Unity | In progress |
| Open reference platform based on the Pollen Robotics Reachy Mini | Planned |
| Authentication (JWT) and authorization (RBAC) | Planned |
| Streaming Interface with WebRTC media | Planned |
| Packages on PyPI, npm, NuGet, and the Unity Package Manager | Planned |
| All 17 basic RoIS HRI Components (v1.0) | Planned |

The [roadmap](docs/roadmap.md) describes each phase and its exit criteria.

## Repository Layout

```
openrois/
├── interfaces/          RoIS types: Python models, JSON Schema, generated TypeScript and C#
├── engine/              Recursive Engine, WebSocket server and client (openrois-engine)
├── gateway/             Gateway process and container image (openrois-gateway)
├── components/
│   ├── core/            Component decorators and result helpers (openrois-components-core)
│   ├── common/          Platform-independent components
│   └── kachaka/         Preferred Robotics Kachaka components (gRPC and ROS 2)
├── sdk/
│   ├── typescript/      Client SDK for web and Node.js (@openrois/sdk)
│   └── csharp/          Client SDK for Unity (OpenRoIS.Sdk, in progress)
├── examples/
│   ├── mock-engine/     RoIS engine test double with simulated components
│   ├── hri-client/      Profile-driven web inspector for any RoIS engine
│   ├── mock-adapter/    Adapter with simulated components
│   └── adapter-template/  Starting point for a new robot adapter
├── apps/hub/            Management dashboard (planned)
├── docs/                White paper, architecture, roadmap, RoIS reference
└── compose.yaml         The gateway with the mock adapter, in Docker Compose
```

## Documentation

| Document | Contents |
|----------|----------|
| [White paper](docs/white-paper.md) | Motivation, design decisions, wire protocol, deployment topologies |
| [Architecture](docs/architecture.md) | Engineering design of the engine, adapters, and components |
| [RoIS reference](docs/rois-reference.md) | Summary of the OMG RoIS Framework 2.0 specification |
| [Roadmap](docs/roadmap.md) | Phases, status, and exit criteria |
| [openrois.org](https://openrois.org/) | The same documentation as a website |

## Development

The RoIS types flow in one direction: **Python models, then JSON Schema, then TypeScript
and C#.** Edit the Python models in `interfaces/python`, regenerate, and never edit the
generated files by hand.

| Stack | Directory | Commands |
|-------|-----------|----------|
| Python types | `interfaces/python` | `pip install -e ".[dev]"`, `pytest`, `mypy src/`, `ruff check src/` |
| TypeScript types | `interfaces/typescript` | `npm install`, `npm run build`, `npm test` |
| C# types | `interfaces/csharp` | `dotnet build`, `dotnet test` |
| TypeScript SDK | `sdk/typescript` | `npm install`, `npm run build`, `npm test` |
| Mock engine | `examples/mock-engine` | `npm install`, `npm test` |
| Engine | `engine` | `pytest`, `ruff check src/ tests/` |
| Gateway | `gateway` | `pytest`, `mypy`, `ruff check src/ tests/ scripts/` |

[`AGENTS.md`](AGENTS.md) documents the conventions and the generation pipeline in
detail.

## Contributing

Contributions are welcome. Reference components for new robots are the natural entry
point, and the [roadmap](docs/roadmap.md) lists work items that can be taken up in
parallel. Please read the [contributing guide](CONTRIBUTING.md) before opening a pull
request.

## Citation

The position paper describing OpenRoIS was submitted to SII 2027 and is under review. Its
preprint is on arXiv as [arXiv:2609.21178](https://arxiv.org/abs/2609.21178), with the DOI
[10.48550/arXiv.2609.21178](https://doi.org/10.48550/arXiv.2609.21178).

```bibtex
@misc{carrera2026openrois,
  author        = {Carrera Villalobos, Sebastian and Arellano, Christopher Nolan and
                   Hitzmann, Arne and Morais Brito, Edilson and Utsumi, Akira and
                   Horikawa, Yukiko and Miyashita, Takahiro and El Hafi, Lotfi},
  title         = {{OpenRoIS}: A Community-Driven Open-Source Middleware Implementing
                   the Robotic Interaction Service ({RoIS}) Framework for Physical
                   Robots and Virtual Agents},
  year          = {2026},
  eprint        = {2609.21178},
  archivePrefix = {arXiv},
  primaryClass  = {cs.RO},
  doi           = {10.48550/arXiv.2609.21178},
  url           = {https://arxiv.org/abs/2609.21178},
  note          = {Submitted to the 2027 IEEE/SICE International Symposium on
                   System Integration (SII 2027)}
}
```

Please also cite the software using the metadata in [`CITATION.cff`](CITATION.cff), which
carries the paper as its preferred citation. The website has the full
[citation guidance](https://openrois.org/docs/project/citing).

## License

OpenRoIS is licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Coarobo GK.
OpenRoIS is developed by Coarobo GK and the OpenRoIS community. OpenRoIS is a trademark
of Coarobo GK. RoIS is a trademark of the Object Management Group.
