# OpenRoIS - Implementation Architecture

> A practical architecture for implementing the OMG **RoIS Framework 2.0** as an
> open-source middleware that lets operator applications control **physical robots,
> virtual avatars, and digital agents** over the internet.
>
> The **primary demonstrated path** is a **web operator application controlling a
> ROS 2 robot** over the internet: a TypeScript web client talks to a Python
> gateway, which bridges to ROS 2 components on the robot. Virtual avatars and
> distributed services remain **fully supported secondary topologies** behind the
> same interfaces.
>
> The architecture is deliberately **paradigm-neutral**: the engine, gateway, and
> client SDK never assume hardware, a world model, or any specific middleware. A
> single **BusAdapter** abstraction lets the same core drive a ROS 2 robot fleet, an
> in-process avatar, or a distributed set of services.
>
> This document is the engineering companion to
> [rois-reference.md](rois-reference.md). The reference explains
> *what the specification says*. This document explains *how we build it*. For the
> milestone roadmap, see [roadmap.md](roadmap.md).

---

## Table of Contents

1. [Goals & Non-Goals](#1-goals--non-goals)
2. [What We Are Building](#2-what-we-are-building)
3. [Architectural Overview](#3-architectural-overview)
4. [Deployment Topologies](#35-deployment-topologies)
5. [Layer 1 - Client & Service Application SDK](#4-layer-1--client--service-application-sdk)
6. [Layer 2 - Gateway (Main HRI Engine)](#5-layer-2--gateway-main-hri-engine)
7. [Layer 3 - Internal Bus (Pluggable)](#6-layer-3--internal-bus-pluggable)
8. [Layer 4 - Hosts: Sub-Engines & Components](#7-layer-4--hosts-sub-engines--components)
9. [The BusAdapter Interface](#75-the-busadapter-interface)
10. [Component Mapping: Robot vs. Avatar](#76-component-mapping-robot-vs-avatar)
11. [Transport Strategy](#8-transport-strategy)
12. [Control Plane vs. Data Plane (Streaming)](#9-control-plane-vs-data-plane-streaming)
13. [Authentication](#10-authentication)
14. [Authorization & Fleet Segmentation](#11-authorization--fleet-segmentation)
15. [Mapping RoIS Interfaces to the Stack](#12-mapping-rois-interfaces-to-the-stack)
16. [End-to-End Message Flows](#13-end-to-end-message-flows)
17. [Proposed Repository Layout](#14-proposed-repository-layout)
18. [Technology Choices](#15-technology-choices)

---

## 1. Goals & Non-Goals

### Goals

- Provide a **conformant RoIS 2.0 implementation** usable across **physical robots,
  virtual avatars, and digital agents**.
- **Demonstrate a web operator application controlling a ROS 2 robot** over the
  internet as the primary, end-to-end reference scenario.
- Keep the **interfaces paradigm-neutral**: the engine and SDK must not assume
  hardware, a world model, or any specific middleware.
- Allow an **operator application in a remote location** to control any RoIS host
  (robot or avatar) securely.
- Expose a **simple client SDK** (TypeScript for web first) so a scenario can be
  written in a few lines, identically regardless of the host paradigm.
- Support **live audio/video** for both telepresence (robot) and rendered avatars.
- Enable **multi-tenant segmentation** through authentication and authorization.

### Non-Goals

- We do **not** invent a new wire protocol. RoIS defines messages, not transport. We
  choose existing transports (WebSocket, DDS, WebRTC).
- We do **not** define media codecs. Streaming media formats are out of RoIS scope.
- We do **not** mandate any single middleware. ROS 2 is the **primary, reference
  robot adapter**. The UniversalBusAdapter (WebSocket + JSON-RPC) is the adapter
  for any non-ROS host (avatars, services). Neither is privileged in the core.

---

## 2. What We Are Building

The output of this effort is **not a protocol and not a single SDK**. It is a
**middleware distribution** with five cooperating artifacts:

| Artifact | Audience | Description |
|----------|----------|-------------|
| **RoIS Interfaces** | Implementers | **Transport-independent** type/interface definitions derived from the normative IDL. Authored as **Python (Pydantic)**, exported to **JSON Schema** (canonical wire format), and generated into **C#** and **TypeScript**. |
| **RoIS Engine + Gateway** | Operators | The **bus-independent** runtime (Python) that manages components and exposes them remotely. |
| **RoIS BusAdapters** | Platform integrators | Pluggable bindings: `ROS 2` (robot, primary), `Universal` (avatars and services, WebSocket + JSON-RPC). All implement one common contract. |
| **RoIS Components** | Integrators | The 17 basic components backed by real perception/actuation libraries, with per-paradigm backends. |
| **RoIS Client SDK** | Application developers | The user-facing library (**TypeScript for web first**, C# and Python second). |

The **Client SDK is the adoption driver**. It is what most users will ever touch,
and it is **identical** whether the host is a robot or an avatar.

---

## 3. Architectural Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 1 - CLIENT                                                     │
│  Web Operator App  +  RoIS TS SDK  +  WebRTC PeerConnection           │
└───────────────┬─────────────────────────────────┬────────────────────┘
                │ WebSocket / TLS                  │ WebRTC (SRTP/DTLS)
                │ (RoIS control plane)             │ (media data plane)
                ▼                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 2 - ROIS GATEWAY  (the "main HRI Engine", bus-independent)     │
│  Auth · RBAC · Session Mgr · WS Server · RoIS Adapter · WebRTC Bridge │
└───────────────┬──────────────────────────────────────────────────────┘
                │ BusAdapter interface (discover · invoke · query · subscribe)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 3 - INTERNAL BUS  (pluggable: choose one adapter per host)     │
└──┬─────────────────────────────────────────────────┬───────────────┘
   ▼                                                   ▼
┌─────────────┐                                   ┌─────────────┐
│ ROS 2 / DDS │                                   │ Universal   │
│ (robot)     │                                   │ (avatar/svc)│
│ PRIMARY     │                                   │             │
│ Sub-engines │                                   │ WS+JSON-RPC │
│ per robot,  │                                   │ host        │
│ Nav2 /      │                                   │ connectors  │
│ perception  │                                   │             │
└─────────────┘                                   └─────────────┘
```

The spec's "main HRI Engine" maps to the **Gateway**. Each "sub HRI Engine" maps to
a **per-host node** (a robot node or a host connector). "HRI Components" map to
whatever the chosen BusAdapter addresses: ROS 2 component nodes or host connector
objects. The client only ever talks to the Gateway. The host topology *and paradigm*
are hidden, exactly as the spec requires.

---

## 3.5 Deployment Topologies

The same four layers compose into different physical deployments. The Client SDK and
Gateway are constant. Only the **BusAdapter** and host layout change. Topology A is
the **primary demonstrated path**. The rest are fully supported alternatives.

### A. Physical Robot + Web Operator (`ROS2BusAdapter`) - PRIMARY

The reference scenario: a **web operator application** controls a **ROS 2 robot**
over the internet. The robot runs a sub-engine and component nodes. The Python
gateway bridges DDS to the remote web client over WebSocket.

```
  Web Operator App ──WS/TLS──► Gateway ──ROS 2/DDS──► Robot (Nav2, YOLO)
     (TS RoIS SDK)               (Python)              person_detection,
                                                        navigation, sysinfo
```

### B. Mixed Fleet (multiple adapters at once)

One gateway can host several adapters simultaneously. For example, a physical robot
(ROS 2) **and** a virtual concierge avatar (UniversalBusAdapter) behind the same SDK
endpoint. This is the strongest proof the interfaces are paradigm-neutral.

```
            ┌─ ROS2BusAdapter ──────► Robot sub-engines (ROS 2 / DDS)
  Gateway ──┤
            └─ UniversalBusAdapter ─► Avatar host connector (WS+JSON-RPC)
```

### C. Distributed Avatar/Service (`UniversalBusAdapter`) - secondary

Avatars and AI services run as host connector processes that register with the
gateway over WebSocket + JSON-RPC. This works for a single avatar on the LAN or
multiple avatars across the network.

```
  Web/Unity  ──WS+JSON-RPC──►  Avatar host connector · GPU service host connector
  (engine+gateway)             (components as host connector processes)
```

---

## 4. Layer 1 - Client & Service Application SDK

The SDK mirrors the five RoIS interfaces (`SystemIF`, `CommandIF`, `QueryIF`,
`EventIF`, and the per-component streaming interface) defined in the normative IDL
(`RoIS_HRI.idl` and `RoIS_Service.idl`).

```
RoIS Client SDK
├─ SystemClient    connect() · disconnect() · getProfile() · getErrorDetail()
├─ CommandClient   search() · bind() · bindAny() · release()
│                  getParameter() · setParameter() · execute() · getCommandResult()
├─ QueryClient     query()
├─ EventClient     subscribe() · unsubscribe() · getEventDetail()  → onNotifyEvent
└─ StreamClient    connectStream() · disconnectStream()
                   suspendStream() · resumeStream() · queryStreamStatus()
```

Target developer experience (TypeScript / web, primary client):

```ts
import { RoISClient } from "@openrois/sdk";

const client = await RoISClient.connect("wss://gateway.example.com", {
  token: await getAccessToken(),
});

// Control a ROS 2 robot: identical API regardless of host paradigm
const pd = await engine.bind("PersonDetection");
pd.on("person_detected", (e) => console.log(`${e.number} people`));
await pd.start();

const nav = await engine.bind("Navigation");
await nav.execute({ target_positions: ["3.0,1.5,0.0"], time_limit: 30 });

const video = await engine.bind("VideoStreaming");
const track = await video.connectStream();    // WebRTC track → <video> element
```

The callback surface comes directly from `ServiceApplicationBase` in the spec:
`notify_error`, `completed`, and `notify_event`.

---

## 5. Layer 2 - Gateway (Main HRI Engine)

The Gateway is the **only internet-facing process** and the **single enforcement
point** for security. It implements the RoIS System/Command/Query/Event interfaces
toward the client and translates them to the bus adapter toward the fleet.

```
┌─────────────────────────────────────────────────────────────────┐
│  RoIS Gateway                                                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Auth Module   │  │ Session       │  │ WebSocket Server       │ │
│  │ • JWT verify │  │ Manager       │  │ • JSON-RPC 2.0         │ │
│  │ • RBAC eval  │  │ • conn state  │  │ • per-conn routing     │ │
│  │ • fleet ACL  │  │ • bind/sub map│  │                        │ │
│  └──────┬───────┘  └──────┬────────┘  └────────────┬───────────┘ │
│         └─────────────────┴────────────────────────┘             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  RoIS Interface Adapter                                   │  │
│  │  SystemIF · CommandIF · QueryIF · EventIF · StreamIF       │  │
│  └───────────────────────────┬──────────────────────────────┘  │
│  ┌───────────────────────────┴──────────────────────────────┐  │
│  │  WebRTC Signaling + Media Bridge (aiortc / mediasoup)     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

Responsibilities:

- **Terminate the remote transport** (WebSocket/TLS) and authenticate every
  connection before any RoIS message is processed.
- **Translate** JSON-RPC RoIS calls to bus adapter operations (service/action/topic
  for ROS 2, WS+JSON-RPC for UniversalBusAdapter hosts).
- **Aggregate profiles** from all authorized sub-engines into one
  `HRI_Engine_Profile` returned by `get_profile()`.
- **Filter** `search()`/`query()` results and **guard** `bind()`/`execute()` per the
  caller's authorization scope.
- **Relay WebRTC signaling** (SDP/ICE) over the same WebSocket connection and bridge
  media through an SFU when needed.

---

## 6. Layer 3 - Internal Bus (Pluggable)

The internal bus is **not fixed**. The engine talks only to a `BusAdapter`
(see [§7.5](#75-the-busadapter-interface)). Concrete adapters bind that contract to a
specific transport. Two production adapters ship with OpenRoIS:

| Adapter | Best for | Discovery | Invoke | Event |
|---------|----------|-----------|--------|-------|
| **ROS 2 / DDS** | Physical robots & fleets | DDS discovery | service / action | topic subscription |
| **Universal** (WS+JSON-RPC) | Avatars, services, any non-ROS host | host self-registration | WS+JSON-RPC call | WS push notification |

A `RosBridgeBusAdapter` (for any ROS via rosbridge) is a future addition.

### ROS 2 / DDS adapter (robot reference)

For physical robots, **ROS 2 over DDS** is the recommended adapter. It is the
dominant research middleware and one of the spec's approved transports.

- RoIS messages map to ROS 2 **services** (synchronous: `query`, `get_parameter`),
  **actions** (long-running: `execute`), and **topics** (async: `notify_event`,
  `notify_stream_status`).
- DDS **discovery** lets sub-engines join/leave dynamically.
- DDS **QoS** policies provide reliability, deadlines, and liveliness suited to
  robotics.
- **DDS-Security** (optional) provides participant authentication, per-topic access
  control, and encryption at the bus level.

Fleet isolation options (ROS 2 adapter):

| Strategy | Isolation | Complexity |
|----------|-----------|------------|
| **Separate DDS domain per fleet** | Strong (no cross-traffic) | Low |
| **DDS-Security permissions per topic** | Granular | Medium |
| **Single domain + Gateway-only filtering** | Weak (bus is trusted) | Lowest |

### Universal adapter (avatar and service reference)

For any non-ROS host (avatars, GPU services, custom hardware), the `UniversalBusAdapter`
uses WebSocket + JSON-RPC. Each host runs a **host connector** process that
registers its components with the gateway at startup. The gateway discovers
components via this self-registration. `invoke`, `query`, and `subscribe` are
WS+JSON-RPC calls to the host connector. This works for a single avatar on the LAN
or multiple avatars distributed across the network. No DDS dependency, no
cross-network multicast requirement.

---

## 7. Layer 4 - Hosts: Sub-Engines & Components

A **host** is anything that provides components: a robot, an avatar process, or a
bank of services. Each host exposes one **sub-engine** plus its components. Every
component implements the `Command` / `Query` / `Event` interfaces it inherits from
`RoIS_Common.idl` (`start` / `stop` / `suspend` / `resume`, `component_status`),
*regardless of paradigm*.

```
┌──────────────────────────────────────┐
│  Sub-Engine: Robot A                  │
│                                      │
│  PersonDetection   → YOLO / OpenCV    │  person_detected(timestamp, number)
│  FaceDetection     → MediaPipe        │  face_detected(timestamp, number)
│  PersonLocalization→ depth + tracker  │  person_localized(…, position_data)
│  SpeechRecognition → Whisper          │  speech_recognized(…, recognized_text)
│  SpeechSynthesis   → espeak / Piper    │  (command: set_parameter speech_text)
│  Navigation        → Nav2             │  (command: target_position, time_limit)
│  Follow            → tracker + Nav2    │  (command: target_object_ref, distance)
│  AudioStreaming    → GStreamer webrtc  │  notify_stream_status(stream_id, status)
│  VideoStreaming    → GStreamer webrtc  │  notify_stream_status(stream_id, status)
└──────────────────────────────────────┘

  Host: Robot A (ROS2BusAdapter)            Host: Avatar (UniversalBusAdapter)
  ─ camera/mic input, physical actuation     ─ webcam input, rendered output
  ─ components are ROS 2 nodes                ─ components are host connector objects
```

The component method categories map to whatever the active adapter provides:

- **Command Method** → ROS 2 action/service or WS+JSON-RPC call.
- **Event Method** → ROS 2 topic or WS push notification.
- **Query Method** → ROS 2 service or WS+JSON-RPC call.

The component's *logic* is the same across adapters. Only the binding differs.

---

## 7.5 The BusAdapter Interface

The **BusAdapter** is the single abstraction that decouples the engine from any
paradigm. The engine, gateway, and SDK never reference ROS, DDS, gRPC, or a game
engine. They depend only on this contract:

```cpp
// The single abstraction that decouples the engine from any paradigm.
class BusAdapter {
public:
    virtual ~BusAdapter() = default;

    // Discovery: how the engine finds components
    virtual ReturnCode_t discover(const Condition_t& filter,
                                   std::vector<RoIS_Identifier>& out) = 0;

    // Command: start/stop/suspend/resume/set_parameter/execute
    virtual ReturnCode_t invoke(const RoIS_Identifier& ref,
                                 const Command& cmd, CommandResult& out) = 0;

    // Query: synchronous component_status / data reads
    virtual ReturnCode_t query(const RoIS_Identifier& ref,
                                const Query& q, Result& out) = 0;

    // Event: async push (notify_event, notify_stream_status)
    virtual ReturnCode_t subscribe(const RoIS_Identifier& ref,
                                    EventSink* sink) = 0;
};
```

| Adapter | Paradigm | Discovery | Invoke | Event |
|---------|----------|-----------|--------|-------|
| **UniversalBusAdapter** | Avatars, services, any non-ROS host | host self-registration (WS) | WS+JSON-RPC call | WS push notification |
| **ROS2BusAdapter** | Physical robot | DDS discovery | service / action | topic subscription |

Because the engine sees only `BusAdapter`, **adding a new paradigm is an additive
adapter, never a rewrite**. Accidental coupling (e.g. baking DDS QoS semantics into
the engine) is structurally prevented.

---

## 7.6 Component Mapping: Robot vs. Avatar

About **70%** of the 17 basic components are *identical* across paradigms. The
perception and speech components run the same ML models whether the input is a robot
camera or a webcam. Only actuation, world model, and stream source differ.

| RoIS Component | Physical Robot | Virtual Avatar | Shared? |
|----------------|----------------|----------------|---------|
| Person Detection | YOLO on camera | YOLO on webcam / virtual sensor | yes |
| Person Localization | depth + tracker | world position / webcam depth | diff coord system |
| Person Identification | InsightFace | InsightFace | yes |
| Face Detection | MediaPipe | MediaPipe | yes |
| Face Localization | MediaPipe face mesh | MediaPipe face mesh | yes |
| Sound Detection | mic VAD | mic VAD | yes |
| Sound Localization | mic-array DOA | mic-array DOA / virtual | diff |
| Speech Recognition | Whisper | Whisper | yes |
| Gesture Recognition | MediaPipe Holistic | MediaPipe Holistic | yes |
| Speech Synthesis | TTS to speaker | TTS to lip-sync to avatar | diff output |
| Reaction | LED / gesture | animation / expression | paradigm-specific |
| Navigation | Nav2 (physical) | NavMesh (virtual) | paradigm-specific |
| Follow | Nav2 + tracker | virtual follow | paradigm-specific |
| Move | `cmd_vel` to motors | transform to avatar | paradigm-specific |
| Audio Streaming | mic to WebRTC | TTS output to WebRTC | diff source |
| Video Streaming | camera to WebRTC | rendered frames to WebRTC | diff source |
| System Information | battery, CPU, joints | FPS, memory, avatar state | diff state |

**Legend:** `yes` = identical. `diff` = same interface, different source/output.
`paradigm-specific` = different implementation per paradigm. The paradigm-specific
rows (Reaction, Navigation, Move, Follow) are exactly the ones a BusAdapter +
per-backend component design keeps cleanly separated.

---

## 8. Transport Strategy

RoIS deliberately separates messages from transport, so we use **the right transport
at each boundary** rather than forcing one everywhere.

| Boundary | Transport | Why |
|----------|-----------|-----|
| Remote client to Gateway | **WebSocket + TLS** | NAT/firewall friendly, browser-native, easy auth, async events. Matches the spec's Annex F.2.3 WebSocket example. |
| Gateway to non-ROS hosts (avatars, services) | **WebSocket + JSON-RPC** | NAT-friendly, self-registration, one protocol for all non-ROS hosts. |
| Gateway to robot fleet | **ROS 2 / DDS** | Reliable pub/sub, QoS, discovery, ecosystem (Nav2, perception). |
| Media (camera/mic or rendered) | **WebRTC (SRTP/DTLS)** | Built-in NAT traversal (ICE/STUN/TURN), adaptive bitrate, encrypted, browser-native. |

Each is selected by the active **BusAdapter** at Layer 3, except WebSocket (always
the remote edge) and WebRTC (always the media plane).

These are complementary, not competing: DDS and WS+JSON-RPC each solve a different
*host* boundary. WebSocket solves the *remote control* boundary. WebRTC solves
*real-time media*.

---

## 9. Control Plane vs. Data Plane (Streaming)

RoIS defines **only the streaming control plane**: `connect_stream`,
`suspend_stream`, `resume_stream`, `disconnect_stream`, `notify_stream_status`, and
the `Stream_Status` enum from `RoIS_Common.idl`. The media data plane is out of
scope, which makes **WebRTC** a natural fit.

```
        RoIS Streaming Control (in scope)        WebRTC Media (out of RoIS scope)
        ───────────────────────────────         ───────────────────────────────
        set_parameter(encoding, transport)  ↔   SDP offer/answer negotiation
        set_parameter(ice candidates)       ↔   ICE / trickle ICE
        connect_stream()                    ↔   RTCPeerConnection open
        notify_stream_status(RUNNING)       ↔   iceconnectionstate = connected
        suspend_stream() / resume_stream()  ↔   RTCRtpSender.track.enabled = false/true
        disconnect_stream()                 ↔   pc.close()
```

WebRTC **signaling travels over the existing WebSocket** RoIS connection (passed as
`set_parameter` arguments), so no separate signaling server is required.

Important distinction the spec preserves:

- **Speech Synthesis** is a *command* component (text to robot speaker locally), not
  a stream.
- **Audio/Video Streaming** are *stream-control* components (live media robot to
  operator), using WebRTC.

### P2P vs. SFU

- **Fleet of 1-3 robots**: peer-to-peer WebRTC is sufficient.
- **Larger fleets**: route media through a **Selective Forwarding Unit** (mediasoup,
  LiveKit). The RoIS streaming control interface is identical either way. The SFU is
  an implementation detail of the Gateway.

---

## 10. Authentication

The spec's `connect()` takes **no parameters**. It assumes a trusted LAN. For remote
access we authenticate **before** any RoIS message is processed, at the WebSocket
upgrade.

```
Client                                   Gateway
  │ 1. POST /auth/token {client_id,…}      │
  │ ─────────────────────────────────────► │
  │ ◄──── {access_token (JWT), expires} ── │
  │                                        │
  │ 2. WS upgrade  Authorization: Bearer … │
  │ ─────────────────────────────────────► │
  │ ◄──── 101 Switching Protocols ──────── │   (401 if token missing/invalid)
  │                                        │
  │ 3. RoIS connect()                      │   now inside the RoIS layer
  │ ─────────────────────────────────────► │
  │ ◄──── ReturnCode_t::OK ─────────────── │
```

Example JWT claims used downstream for authorization:

```json
{
  "sub": "operator-alice",
  "roles": ["operator"],
  "fleet_scope": ["warehouse-north", "lab-b"],
  "components": ["person_detection", "navigation", "video_streaming"],
  "iat": 1749500000,
  "exp": 1749503600
}
```

| Approach | Pros | Cons |
|----------|------|------|
| **Gateway-internal JWT** | No external deps, simplest | Single trust domain |
| **OIDC provider** (Keycloak, Auth0, Dex) | SSO, federation, user mgmt | Extra infrastructure |
| **mTLS** (client certs) | Strongest auth | Cert provisioning for browsers |

Recommended path: gateway-internal JWT for the prototype, then OIDC provider for
multi-tenant deployments.

---

## 11. Authorization & Fleet Segmentation

Authorization is enforced **per RoIS operation** inside the Gateway. The spec's
`Condition_t` (a string carrying an ISO 19143 `QueryExpression`) and `component_ref`
are the natural enforcement points.

### RBAC Model

| Role | Fleet Scope | Component Scope |
|------|-------------|-----------------|
| **admin** | all | all |
| **operator** | assigned | assigned (incl. actuation) |
| **viewer** | assigned | detection + streaming only |
| **maintenance** | assigned | system_information |

### Enforcement Points

| Interface / Op | Enforcement |
|----------------|-------------|
| `connect()` | Verify JWT. Expose only sub-engines within `fleet_scope`. |
| `search(condition)` | Filter `component_ref_list` to authorized fleet + components. |
| `bind(component_ref)` | Reject refs outside scope (`BAD_PARAMETER` / `UNSUPPORTED`). |
| `execute(command_unit_list)` | Validate every `component_ref` in the sequence. |
| `query(query_type, condition)` | Filter results to authorized fleets (e.g. `robot_position`). |
| `subscribe(event_type, condition)` | Deliver `notify_event` only for authorized sources. Scope `subscribe_id` to the session. |
| `connect_stream()` | Require `streaming` scope. SFU enforces per-stream ACL. |

### Worked Example

```
Org: Acme Robotics
├── Fleet warehouse-north  → Robot-A1, Robot-A2
├── Fleet warehouse-south  → Robot-B1, Robot-B2
└── Fleet lab-b            → Robot-C1
```

- **Alice** (`operator`, scope `warehouse-north`): `search()` returns only A1/A2.
  `bind("Robot-B1/navigation")` is rejected.
- **Bob** (`admin`, scope `*`): sees and controls everything.
- **Carol** (`viewer`, scope `warehouse-north,south`): `search()` returns detection +
  streaming only. `bind(navigation)` is rejected. `connect_stream(video)` is allowed.

Because the Gateway filters at `search()`, robots outside a caller's scope are
**invisible**. The caller cannot discover or address them.

### Defense in Depth

1. **TLS** on the remote edge.
2. **JWT/OIDC** authentication at WebSocket upgrade.
3. **RBAC** authorization per RoIS operation in the Gateway.
4. **DDS-Security** (or per-fleet DDS domains) on the bus.
5. **DTLS/SRTP** on WebRTC media.

---

## 12. Mapping RoIS Interfaces to the Stack

| RoIS Interface (IDL) | Client SDK | Gateway | Bus (via BusAdapter) |
|----------------------|-----------|---------|----------------------|
| `SystemIF` | `SystemClient` | WS handler + auth | `discover()` (registry/DDS/gRPC) |
| `CommandIF` | `CommandClient` | RBAC filter + adapter | `invoke()` (call/action/unary) |
| `QueryIF` | `QueryClient` | result filter | `query()` (call/service/unary) |
| `EventIF` | `EventClient` | subscription router | `subscribe()` (callback/topic/stream) |
| `ServiceApplicationBase` (`notify_*`, `completed`) | SDK callbacks | WS push | event sink (callback/topic/stream) |
| Streaming `Command`/`Query`/`Event` | `StreamClient` | WebRTC bridge | GStreamer/aiortc or rendered source |

---

## 13. End-to-End Message Flows

### 13.1 Authenticated Bind + Execute + Event

```
Web App            Gateway                ROS 2 Bus           Robot-A1
  │  bind(robot-a1/pd) + token │              │                  │
  │ ─────────────────────────► │              │                  │
  │            verify JWT, check fleet+role+component             │
  │                            │  /robot_a1/pd/bind              │
  │                            │ ────────────►│ ───────────────► │
  │                            │ ◄────────────│ ◄─────────────── │
  │ ◄──────── OK ───────────── │              │                  │
  │  execute(start)            │              │                  │
  │ ─────────────────────────► │  /robot_a1/pd/execute (action)  │
  │                            │ ────────────►│ ───────────────► │
  │ ◄──── command_id ───────── │              │                  │
  │                            │  ◄ person_detected (topic) ───── │
  │ ◄── notify_event(number=2) │              │                  │
```

### 13.2 Video Stream Setup (WebRTC)

```
Web App                         Gateway                     Robot-A1
  │ bind(VideoStreaming)          │                            │
  │ ────────────────────────────► │ ──────────────────────────►│
  │ set_parameter(SDP offer, ICE) │                            │
  │ ────────────────────────────► │  negotiate via webrtcbin   │
  │ ◄──── set_parameter(SDP answer)│ ◄──────────────────────────│
  │ connect_stream()              │                            │
  │ ────────────────────────────► │                            │
  │ ═══════ WebRTC media (SRTP) ══╪════════════════════════════│
  │ ◄── notify_stream_status(RUNNING) ─                         │
```

---

## 14. Proposed Repository Layout

Directories use **kebab-case**. Each language package follows its own ecosystem
convention internally (Python `snake_case`, C# `PascalCase`, npm `@scope/kebab`).

```
openrois/
├── interfaces/              # Shared types: single source of truth
│   ├── schema/             #   Canonical JSON Schema (the wire contract)
│   ├── python/             #   Pydantic models (authored here), exports schema
│   ├── csharp/             #   Generated C# types (OpenRoIS.Interfaces)
│   └── typescript/         #   Generated TS types (@openrois/interfaces)
├── engine/                  # Bus-independent engine (Python): lifecycle, bind/execute
├── bus/                     # BusAdapter contract + reference adapters
│   ├── ros2/               #   ROS2BusAdapter (Python/rclpy), PRIMARY
│   └── universal/          #   UniversalBusAdapter (WS+JSON-RPC, avatars and services)
├── gateway/                 # WebSocket server (Python), RoIS to BusAdapter, WebRTC bridge
│   ├── auth/               #   JWT/OIDC verification
│   ├── rbac/               #   fleet + component authorization policy
│   └── webrtc/             #   aiortc / mediasoup signaling + media
├── components/              # Component nodes (Python), per-paradigm backends
│   ├── person-detection/   #   robot: YOLO, avatar: YOLO on webcam
│   ├── navigation/         #   robot: Nav2, avatar: NavMesh
│   ├── move/               #   robot: cmd_vel, avatar: transform
│   ├── system-information/ #   robot: TF/odom/diagnostics
│   ├── face-detection/     #   MediaPipe (shared)
│   ├── speech-synthesis/   #   robot: Piper to speaker, avatar: TTS to lip-sync
│   ├── reaction/           #   robot: LED/gesture, avatar: animation
│   └── ...                 #   remaining basic components
├── sdk/                     # client SDKs
│   ├── typescript/          #   @openrois/sdk (npm, web + Node, PRIMARY)
│   └── csharp/              #   OpenRoIS.Sdk (NuGet + UPM, Unity)
├── examples/                # runnable examples and test tools
│   ├── mock-engine/       #   mock WebSocket engine (JSON-RPC test double for SDKs)
│   ├── web-operator/       #   web operator app driving a ROS 2 robot (MVP demo)
│   └── mock-robot/         #   ROS 2 mock sub-engine + component nodes
└── docs/                    # documentation
```

---

## 15. Technology Choices

| Concern | Recommended | Alternatives |
|---------|-------------|--------------|
| Operator client | **Web (TypeScript)** | Unity (C#), Godot |
| Robot middleware | **ROS 2 (Humble/Jazzy) over DDS** | CORBA, RTC |
| Engine / gateway language | **Python (rclpy, asyncio)** | C++ (rclcpp), Node |
| Interface source of truth | **Pydantic to JSON Schema to C#/TS** | Protobuf, raw IDL |
| Avatar host | Unity / Godot / Web (Three.js, Babylon.js) | Unreal, MMDAgent, Live2D |
| Internal bus (robot) | ROS 2 / DDS | — |
| Internal bus (avatar/services) | WebSocket + JSON-RPC (UniversalBusAdapter) | — |
| Remote transport | WebSocket + TLS | gRPC-web, MQTT |
| RPC envelope | JSON-RPC 2.0 | Protobuf, CBOR |
| Media | WebRTC (aiortc / GStreamer webrtcbin) | RTSP, HLS |
| SFU (large fleets) | mediasoup, LiveKit | Janus |
| Auth | Keycloak (OIDC) / gateway JWT | Auth0, Dex, mTLS |
| Perception | YOLO, MediaPipe, Whisper | platform-specific |
| Navigation | robot: Nav2, avatar: NavMesh | custom |
| Speech synthesis | Piper, VOICEVOX, Coqui TTS | cloud TTS |

---

*This is an engineering design document for the OpenRoIS project. For the
specification summary, see [rois-reference.md](rois-reference.md).
For the milestone roadmap, see [roadmap.md](roadmap.md). For authoritative
requirements, consult the OMG specification at <https://www.omg.org/spec/RoIS/2.0/Beta2>.*