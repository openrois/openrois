# Robotic Interaction Service (RoIS) Framework - Reference

> An in-depth reference for the OMG **Robotic Interaction Service (RoIS) Framework**, Version 2.0.
>
> - **OMG Document Number:** formal/26-06-03 (June 2026)
> - **Normative reference:** <https://www.omg.org/spec/RoIS/2.0>
> - **Machine-readable files:** <https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>
> - **Copyright:** JARA, ETRI, KAR, and Object Management Group, Inc.

This document summarizes and explains the specification that the machine-readable
artifacts at <https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>
implement (IDL/HPP headers, component XML profiles, the `XML-Profiles.xsd`
schema, and the `OWL.ttl` ontology).

---

## Table of Contents

1. [What RoIS Is](#1-what-rois-is)
2. [Why It Exists](#2-why-it-exists)
3. [Conformance](#3-conformance)
4. [Core Concepts & Terminology](#4-core-concepts--terminology)
5. [Framework Structure](#5-framework-structure)
6. [The Communication Framework](#6-the-communication-framework)
7. [The Five Interfaces](#7-the-five-interfaces)
8. [Message Data Model](#8-message-data-model)
9. [RoIS Profiles](#9-rois-profiles)
10. [Basic HRI Components](#10-basic-hri-components)
11. [The RoIS / RoSO Ontology](#11-the-rois--roso-ontology)
12. [Extensibility: User-Defined Components](#12-extensibility-user-defined-components)
13. [Platform-Specific Models & Transports](#13-platform-specific-models--transports)
14. [Map to the Machine-Readable Files](#14-map-to-the-machine-readable-files)
15. [Glossary](#15-glossary)
16. [Known Normative Divergences](#16-known-normative-divergences)
17. [How OpenRoIS Implements RoIS](#17-how-openrois-implements-rois)

---

## 1. What RoIS Is

RoIS defines a **platform-independent model (PIM)** of a framework that handles the
messages and data exchanged between **human-robot interaction (HRI) service
components** and **service applications**.

The central idea: a service application interacts with robots on the **symbolic
level** ("a person was detected", "approach the person", "say this message")
rather than on the **physical level** (camera pixels, motor commands). All
hardware-specific concerns are hidden behind standardized interfaces.

> **Symbolic data only.** Messages must not carry raw sensor data such as image or
> audio buffers. Symbolic results can be fed directly into conditional logic
> (`if`/`switch`) in a robot scenario.

New in 2.0:

- Functional components are described using the **RoSO** (Robotic Service Ontology)
  and **RoIS** ontologies.
- The lower surface of the messaging layer was removed from the messaging section
  and PSMs.
- **Streaming** functional components (audio/video) were added for *cybernetic
  avatar* services.

---

## 2. Why It Exists

Traditionally, a service application is written against one robot's specific
hardware functions (e.g., `find face`, `wheel control`). Any hardware change forces
an application rewrite, which kills reusability.

RoIS inserts a **standard interface and framework** between the application and the
robot. The same `Service App` then works across different robot platforms (Robot 1
with face recognition + wheels, Robot 2 with RFID detection + legs) with little
modification, because both expose the same abstract HRI Components (e.g., "who is
there?", "approach the person").

---

## 3. Conformance

An implementation claiming conformance shall:

- Provide the interfaces described in **§8.2 RoIS Interface**.
- Support the message data structures described in **§8.3 RoIS Profiles**.
- Support the **Common Messages** of **§8.4** *for the basic components it
  implements* (it need not implement every basic component).
- Handle component profiles described as **XML files** (the XML-Profile PSM
  machine-readable files) and the messages defined therein.

---

## 4. Core Concepts & Terminology

| Term | Meaning |
|------|---------|
| **HRI** | Human-Robot Interaction. |
| **HRI Component** | An abstract object that uses sensors/actuators to provide a specific HRI function (person detection, speech, etc.). Internal structure is encapsulated. |
| **Basic HRI Component** | An HRI Component providing a *commonly implemented* HRI function. 15+ are defined normatively. |
| **User-defined HRI Component** | Any HRI Component providing a function beyond the basic set. |
| **HRI Engine** | An object that **manages** HRI Components and mediates their functions to service applications. A physical unit. |
| **Service Application** | Software that controls HRI Components (via the HRI Engine) to implement a robot scenario. |
| **Detection / Localization / Identification** | Return *number of* targets / *locations of* targets / *identifiers of* targets, respectively. |
| **Identifier (ID)** | A token (integer or string) for an object, always paired with its Reference Coordinate System (RCS). Can be *permanent* or *temporary*. |

---

## 5. Framework Structure

The framework is organized in three conceptual layers:

```
Total System   →  [HRI Engine (main)]            ← the single entry point for apps
Logical Layer  →  [HRI Engine (sub)] × N         ← physical units (Robot1, Room1, Robot2…)
                  [HRI Component]    × N          ← abstract functions per sub HRI Engine
Implementation →  Sensors / Actuators            ← cameras, mics, LRF, wheels, legs…
```

Key rules:

- A system may consist of **multiple physical units**. Each is a **sub HRI Engine**.
  The whole system is the **main HRI Engine** that contains them.
- The application talks to **only the main HRI Engine**. Selection and switching
  between sub HRI Engines and components happens **engine-side** and is invisible to the
  application.
- One physical unit can host more than one function, so physical units and
  functional units are defined separately (no one-to-one mapping).

---

## 6. The Communication Framework

### 6.1 Messaging

Data exchanged across any interface is called a **message**. Messages carry only
symbolic data. To use an engine, the application must first learn the engine's
configuration and available messages - this is published via **Profiles** (§9).

### 6.2 Use of Other Component Models

RoIS defines the *messages*, not the *transport*. C++ and CORBA PSMs define method
signatures only. RoIS messages can run over **CORBA, RTC, ROS/ROS2 (DDS)**, or any
transport. Interoperability is scoped to within a single transport. An example
WebSocket transport is given for cybernetic avatar services (Annex F.2.3).

### 6.3 Streaming Channels

Semi-autonomous / avatar robots operated remotely need to send audio and video to
operators. RoIS does not define stream formats but **does** define how to manage and
control streams via the Audio/Video Streaming components (§8.4.18-19).

---

## 7. The Five Interfaces

The RoIS Framework exposes one System interface plus three information-exchange
interfaces, plus a Streaming interface layered on the others.

| Interface | Direction & Style | Key Operations |
|-----------|-------------------|----------------|
| **System** | Connection management, synchronous | `connect`, `disconnect`, `get_profile`, `get_error_detail` |
| **Command** | App to Engine, async execution | `search`, `bind`, `bind_any`, `release`, `get_parameter`, `set_parameter`, `execute`, `get_command_result` |
| **Query** | App to Engine, synchronous | `query` |
| **Event** | Engine to App, async notifications | `subscribe`, `unsubscribe`, `get_event_detail`, `notify_event` |
| **Streaming** | Two-way stream control | `connect_stream`, `disconnect_stream`, `suspend_stream`, `resume_stream`, `query_stream_status`, `notify_stream_status` |

### 7.1 Return Codes (`ReturnCode_t`)

`OK`, `ERROR`, `BAD_PARAMETER`, `UNSUPPORTED`, `OUT_OF_RESOURCES`, `TIMEOUT`.
`UNSUPPORTED` is in the IDL but not in the specification's return code table (§16).

Each PSM may map these to return codes or exceptions.

### 7.2 System Interface

- `connect()` establishes the session. `disconnect()` ends it. No messages may flow
  before connect completes or after disconnect is requested (synchronous).
- `get_profile(condition, profile)` retrieves engine/component profiles.
- Errors arrive asynchronously via `notify_error(error_id, error_type)`. Details
  through `get_error_detail(error_id, …)`. Engine error notifications are valid from
  `connect()` until `disconnect()`.

### 7.3 Command Interface - Bind / Execute / Release

Because a component may be shared by multiple applications, command usage follows a
three-step reservation pattern:

1. **BindComponent** - `search(condition)` returns candidate `component_ref`s, then
   `bind(component_ref)`. Or `bind_any(condition)` lets the engine auto-select.
   Optionally `get_parameter`/`set_parameter`.
2. **Execute** - `execute(command_unit_list)` sends a command message. The
   specification text says the engine returns a `command_id` immediately, while the
   IDL has the application name each command (§16). The operation runs
   asynchronously. Completion arrives via `completed(command_id, status)`. Detailed
   results via `get_command_result(command_id, …)`.
3. **Release** - `release(component_ref)` frees the component.

The `command_unit_list` can express **sequential and parallel** command operations
(see Annex B / `CommandUnitSequence`).

Component error notifications are valid from `bind()`/`bind_any()` until `release()`
(or `subscribe()`→`unsubscribe()` for events).

### 7.4 Query Interface

`query(query_type, condition, results)` is **synchronous**, because robot-scenario
state transitions usually depend synchronously on queried info. May be called any
time.

### 7.5 Event Interface

- `subscribe(event_type, condition)` → returns a `subscribe_id`.
- The engine calls `notify_event(event_id, event_type, subscribe_id, expire)` when
  the event occurs.
- `get_event_detail(event_id, …)` fetches details (subject to the `expire` time
  limit).
- `unsubscribe(subscribe_id)` cancels. Duplicate subscribe/unsubscribe requests are
  silently ignored (no error).

### 7.6 Streaming Interface

The application drives the stream: `connect_stream` (after `set_parameter` for
encoding/transport), `suspend_stream`/`resume_stream`, `disconnect_stream`. The
engine may asynchronously push `notify_stream_status` to suspend/resume/close.
Transport and encoding details are out of RoIS scope. Stream status values:
`STREAMING_NOT_RUNNING`, `STREAMING_NOT_CONNECTED`, `STREAMING_RUNNING`,
`STREAMING_SUSPENDED`, `STREAMING_RESUMED`.

---

## 8. Message Data Model

"Message data" is the payload for each interface:

| Message | Exchanged by | Notes |
|---------|--------------|-------|
| **Command Message** | `execute()` | `component_ref`, `command_type`, `command_id`, `arguments` |
| **Command Result Message** | `get_command_result()` | `command_id`, `condition`, `results` |
| **Query Message** | `query()` | `query_type`, `condition`, `results` |
| **Event Message** | `notify_event()` | `event_id`, `event_type`, `subscribe_id`, `expire` |
| **Event Detail Message** | `get_event_detail()` | `event_id`, `condition`, `results` |
| **Error Message** | `notify_error()` | `error_id`, `error_type`, … |
| **Error Detail Message** | `get_error_detail()` | `error_id`, `condition`, `results` |

Supporting data classes:

- **`RoIS_Identifier`** (derived from `MD_Identifier` [ISO 19115]) - an ID plus its
  reference codebook URI and version.
- **`CommandUnitSequence`** → ordered list of **`CommandUnit`** (abstract).
  Concrete subtypes: **`CommandMessage`** and **`ConcurrentCommands`** (which holds
  a `command_list` of `CommandMessage`s executed concurrently).
- **`Parameter`** (`name`, `data_type_ref`, `value`), and the lists
  **`ArgumentList`**, **`ResultList`**, **`ParameterList`**.

Exception types for `notify_error`: `ENGINE_INTERNAL_ERROR`,
`COMPONENT_INTERNAL_ERROR`, `COMPONENT_NOT_RESPONDING`, `USER_DEFINED_ERROR`.
Completion statuses: `OK`, `ERROR`, `ABORT`, `OUT_OF_RESOURCES`, `TIMEOUT`.

---

## 9. RoIS Profiles

Profiles let the application discover what an engine offers. There are **four**
types, composed hierarchically:

```
HRI_Engine_Profile  ──contains──►  HRI_Component_Profile  ──contains──►  Message_Profile
        │                                  │                                   │
        └── Parameter_Profile              └── Parameter_Profile               └── Parameter_Profile
        └── sub_profile (engine)           └── sub_component (component)
```

| Profile | Defines |
|---------|---------|
| **Parameter_Profile** | `name`, `data_type_ref`, optional `default_value`, `description`. |
| **Message_Profile** | `name` + result/argument parameters. Subtypes per interface: `Command_Message_Profile` (adds `argument`), `Command_Result_Message_Profile` (adds `timeout`), `Query_Message_Profile`, `Event_Detail_Message_Profile`, `Error_Detail_Message_Profile`. |
| **HRI_Component_Profile** | Messages + parameters of one component. May nest `sub_component` profiles. Derived from `IO_IdentifiedObject` [ISO 19111]. |
| **HRI_Engine_Profile** | Components + parameters of one engine. May nest `sub_profile` engines. Derived from `IO_IdentifiedObject` [ISO 19111]. |

Profiles are authored in **XML** (Annex A). Conditions used in `search`, `query`,
`subscribe`, etc., are **`QueryExpression`** values per **ISO 19143** (filter
encoding. Annex E shows empty / property-value / location-name / location-coordinate
filters). OpenRoIS writes conditions in a subset of CQL2-Text instead (§17.4).

---

## 10. Basic HRI Components

Every basic component (except System Information) shares `RoIS_Common`:

- **Command methods:** `start`, `stop`, `suspend`, `resume`.
- **Query method:** `component_status` → `Component_Status` ∈ {`UNINITIALIZED`,
  `READY`, `BUSY`, `WARNING`, `ERROR`}.

| # | Component | Function (summary) |
|---|-----------|--------------------|
| 1 | **System Information** | Status & location of the engine/physical unit (`robot_position`, `engine_status`). *No `RoIS_Common`.* |
| 2 | **Person Detection** | Notifies number of people when it changes. |
| 3 | **Person Localization** | Notifies positions of people. Params: detection threshold, minimum interval. |
| 4 | **Person Identification** | Notifies IDs of detected people. |
| 5 | **Face Detection** | Notifies number of faces. |
| 6 | **Face Localization** | Notifies positions of faces. |
| 7 | **Sound Detection** | Notifies number of sound sources. |
| 8 | **Sound Localization** | Notifies positions of sound sources. |
| 9 | **Speech Recognition** | Recognizes speech → text (string). Non-grammar variant. W3C-SRGS variant in Annex C. |
| 10 | **Gesture Recognition** | Recognizes gestures → gesture IDs. |
| 11 | **Speech Synthesis** | Generates speech from text / W3C-SSML. Voice character, volume, language. |
| 12 | **Reaction** | Executes a reaction specified by reaction ID. |
| 13 | **Navigation** | Moves toward target position(s). `time_limit`, `routing_policy`. |
| 14 | **Follow** | Follows a target object. `distance`, `time_limit`. |
| 15 | **Move** | Moves a short line or curve. Distance/orientation/time. |
| 16 | **Audio Streaming** | Controls audio streams between engine and services. |
| 17 | **Video Streaming** | Controls video streams between engine and services. |

Method categories per component follow the PIM convention:

- **Command Method** → arguments via `set_parameter` / `execute`.
- **Event Method** → results delivered by `notify_event` (e.g.,
  `person_detected(timestamp, number)`).
- **Query Method** → results delivered by `query` / `get_parameter`.

Location/position data uses **`Data` [RLS]** (Robotic Localization Service).
Timestamps use **`DateTime` [ISO 8601]**. Languages use **ISO 639-1**.

---

## 11. The RoIS / RoSO Ontology

RoIS 2.0 reuses and extends **RoSO** (Robotic Service Ontology), which itself builds
on the OMG **Commons Ontology Library** and the **LCC** (Languages, Countries, Codes)
specification.

- **Component classes** are subclasses of `roso:Sensing`, `roso:Actuation`, or
  `roso:Function` (e.g., `PersonDetection ⊑ roso:Sensing`,
  `SpeechSynthesis ⊑ roso:Actuation`, `AudioStreaming ⊑ roso:Function`).
- **Properties** (subproperties of `roso:hasAttribute`, domain `roso:Function`)
  describe component requirements, e.g.:
  - `hasDetectionRegion` → `roso:Region`
  - `hasDetectionThreshold` → `roso:SpatialInterval`
  - `hasDetectionTimelimit` / `hasMaximumInterval` / `hasMinimumInterval` →
    `cmns-dt:TimeInterval`
  - `hasMinimumDistance` → `roso:SpatialInterval`
  - `hasTarget` → `cmns-pts:Agent ∪ roso:PhysicalThing`
  - `hasTimeLimit` → `cmns-dt:TimeInstant`

Ontology IRI: `https://www.omg.org/spec/RoIS/RoboticInteractionServiceComponentOntology/`
(see `OWL.ttl` in the OMG machine-readable files).

The notation in class tables follows a subset of OWL 2 / Description Logic (∩, ∪,
∀R.C, ∃R.C, cardinality restrictions, etc.).

---

## 12. Extensibility: User-Defined Components

Annex C demonstrates how to define components beyond the basic set, reusing
`RoIS_Common` and the profile mechanism:

- **Speech Recognition (W3C-SRGS)** - grammar-configurable, returns N-best /
  lattice results.
- **Person Gender Identification** (ISO 5218 codes) and **Person Age Recognition**
  (lower/upper age limits).
- **Wheelchair Robot** - extends Navigation with brake/status events.
- **Approach / Leave / Touch / Touch Detection** - fine-grained manipulation
  components used in a vital-data-measurement scenario.

An HRI Component Profile can **include another** profile via `sub_component`, so an
extended component (e.g., `person_monitor`) can reuse `person_detection`'s messages
and just add new ones (e.g., `person_disappeared`).

---

## 13. Platform-Specific Models & Transports

- **C++ PSM** and **CORBA PSM** define method signatures only.
- **XML-Profile PSM** - profiles serialized as XML, validated by
  `XML-Profiles.xsd`.
- Transports demonstrated/allowed: CORBA, OMG RTC, ROS/ROS2 over DDS, and WebSocket
  (cybernetic avatar example).

Normative references include: Commons 1.1, CORBA 3.4, DDS 1.4, ISO 639/8601/14882/
19111/19115/19143/19784, OWL 2, RDF 1.1 (+Schema, Turtle), RLS 1.1, RTC 1.1, UML
2.5.1, W3C-SRGS, W3C-SSML.

---

## 14. Map to the Machine-Readable Files

The spec's PSMs correspond to the OMG machine-readable files at
<https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>:

| Artifact | Files |
|----------|-------|
| **Common PIM/IDL/C++** | `RoIS_Common.{idl,hpp}`, `RoIS_HRI.{idl,hpp}`, `RoIS_Service.{idl,hpp}` |
| **Per-component IDL/C++** | e.g. `RoIS_Person_Detection.*`, `RoIS_Person_Localization.*`, `RoIS_Person_Identification.*`, `RoIS_Face_Detection.*`, `RoIS_Face_Localization.*`, `RoIS_Sound_Detection.*`, `RoIS_Sound_Localization.*`, `RoIS_Speech_Recognition.*`, `RoIS_Speech_Synthesis.*`, `RoIS_Gesture_Recognition.*`, `RoIS_Reaction.*`, `RoIS_Navigation.*`, `RoIS_Follow.*`, `RoIS_Move.*`, `RoIS_Audio_Streaming.*`, `RoIS_Video_Streaming.*`, `RoIS_System_Information.*` |
| **Component XML profiles** | `PersonDetection.xml`, `PersonLocalization.xml`, `FaceDetection.xml`, `Navigation.xml`, `AudioStreaming.xml`, `RoISCommon.xml`, `Model.xml`, … |
| **Profile schema** | `XML-Profiles.xsd` |
| **Ontology** | `OWL.ttl` |

---

## 15. Glossary

- **PIM** - Platform Independent Model.
- **PSM** - Platform Specific Model (C++, CORBA, XML-Profile).
- **RCS** - Reference Coordinate System (namespace for IDs).
- **RoSO** - Robotic Service Ontology.
- **RLS** - Robotic Localization Service (used for position `Data`).
- **CA** - Cybernetic Avatar (a partly/fully tele-operated robot).
- **HRI Engine (main/sub)** - manager of components. The main engine is the single
  point of contact for applications.

---

## 16. Known Normative Divergences

The normative files and the specification text occasionally disagree. Where the IDL
and an XML profile conflict, the OpenRoIS implementation follows the **XML profile**
(the authoritative component-profile PSM), with one recorded exception (item 4). Where
the specification text and the IDL conflict, it follows the IDL. Known divergences:

1. **Navigation `target_position` vs `target_positions`**: The IDL
   (`RoIS_Navigation.idl`) declares the parameter as `target_position` (singular),
   while the XML profile (`Navigation.xml`) uses `target_positions` (plural). The
   implementation uses `target_positions` (XML profile).

2. **Navigation `reached_target` event**: The IDL `Navigation::Event` interface is
   empty (inherits from `RoIS_Common::Event` but defines no methods). The XML profile
   defines a `reached_target` event with `target` (string) and `is_final_target`
   (bool) results. The implementation includes `NavigationReachedTargetEvent`
   (XML profile).

3. **`ConcurrentCommands` structure**: The XSD defines `ConcurrentCommandsType` with
   a `command_list` of `CommandMessageType` (a flat list of commands executed
   concurrently). A `BranchType` is defined in the XSD but is not used by
   `ConcurrentCommandsType`. Earlier versions of this reference described
   `ConcurrentCommands` as holding `Branch`es. This has been corrected to match the
   XSD.

4. **Reaction `reaction_ref`**: `RoIS_Reaction.idl` takes a list in
   `set_parameter(in RoIS_IdentifierList reaction_ref)` and returns one identifier in
   `get_parameter(out RoIS_Identifier reaction_ref, …)`. `Reaction.xml` declares the
   `reaction_ref` parameter as a single `RoISIdentifier`, and `available_reactions` as a
   query message, while the IDL returns it from `get_parameter`. The implementation
   follows the IDL operation signatures (`ReactionSetParameter`,
   `ReactionGetParameterResult`). This is the exception to the XML profile rule: the
   profile does not say how a `set_parameter` call carries several reactions, and the
   IDL does. The `REACTION_PROFILE` constant is a profile, so it follows `Reaction.xml`.

5. **`UNSUPPORTED` return code**: The IDL `ReturnCode_t` has six values, including
   `UNSUPPORTED`. The return code table of the specification text (Table 8.1 in the
   2.0-beta2 document) lists five and omits `UNSUPPORTED`. The implementation follows
   the IDL.

6. **`execute` and `command_id`**: The specification text (Command Interface, §8.2.2.2
   in the 2.0-beta2 document) says the engine returns a `command_id` when it receives
   `execute()`. The IDL operation
   `execute(in CommandUnitSequence command_unit_list)` has no out parameter, and every
   command message in the XSD carries a required `command_id`. The implementation
   follows the IDL and the XSD: the application names each command, and `completed`
   and `get_command_result` use that name.

7. **`Component_Status` and `Component_Status_t`**: `RoISCommon.xml` types the result of
   `component_status` as `Component_Status`, the enumeration, and `SystemInformation.xml`
   types the `status` result of `engine_status` the same way. `RoIS_Common.hpp` declares
   `component_status(Component_Status& status)`. `RoIS_Common.idl` declares
   `component_status(out Component_Status_t status)` with
   `typedef long Component_Status_t`, a number. The implementation follows the XML
   profiles: a status travels as the enumerator name, for example `READY`.

8. **SystemInformation and RoIS_Common**: `RoIS_System_Information.idl` derives its
   `Query` interface from `RoIS_Common::Query`, which declares `component_status`.
   `SystemInformation.xml` includes no RoIS_Common profile and lists only
   `robot_position` and `engine_status`. The implementation follows the XML profile:
   SystemInformation has no `component_status` query and no RoIS_Common commands.

---

## 17. How OpenRoIS Implements RoIS

This section describes OpenRoIS, not the specification. It records the choices
OpenRoIS makes where the specification leaves them to the platform-specific model, and
the few places where it adds to the specification. The interfaces packages
(`interfaces/`) define all of it. The Python engine, the TypeScript SDK and the mock
engine are moving to this method catalog (in progress).

### 17.1 Wire Binding

RoIS defines operations, not a transport (§6.2). OpenRoIS carries them as JSON-RPC 2.0
messages, over WebSocket between processes.

- Each operation of the System, Command, Query and Event interfaces is a JSON-RPC
  method named `rois.<interface>.<operation>`, with `system`, `command`, `query` and
  `event` as the interface names, for example `rois.command.bind_any`. The Streaming
  interface is not modelled yet (planned). An engine answers any `rois.stream.*` method
  with the JSON-RPC error `METHOD_NOT_FOUND`.
- The `in` parameters of an operation are the method's `params`, named as in the IDL.
  The `result` holds `return_code` and one field per `out` parameter.
- A RoIS failure is a normal result whose `return_code` is not `OK`, with its out fields
  empty. JSON-RPC errors are only for protocol faults: unparseable JSON (`-32700`), an
  invalid request (`-32600`), an unknown method (`-32601`), params that fail validation
  (`-32602`) and internal errors (`-32603`).
- The `ServiceApplicationBase` callbacks are JSON-RPC notifications from the engine:
  `rois.system.notify_error`, `rois.command.completed` and `rois.event.notify_event`,
  with the IDL `in` parameters as their params.
- `execute` carries its `command_unit_list` as JSON that follows
  `CommandUnitSequenceType` in `XML-Profiles.xsd`: a list of command messages
  (`component_ref`, `command_type`, `command_id`, `arguments`, `delay_time`) and
  concurrent groups (`command_list`, `delay_time`). The IDL types it as a string that
  holds the XML.
- `get_profile` returns the engine profile as JSON that follows `HRIEngineProfileType`
  in `XML-Profiles.xsd`. The IDL types `HRI_Engine_Profile` as a string that holds the
  XML document.
- `command_type` is a string, as in the IDL and the XSD. The standard names are
  `start`, `stop`, `suspend` and `resume` (`RoIS_Common`) and `set_parameter`. A
  component may define others.

The method table lives in `openrois.interfaces.catalog` and in
`interfaces/schema/catalog.json`, which the TypeScript and C# packages are generated
from.

### 17.2 Extension Policy

OpenRoIS adds to the specification only where an addition passes all five tests:

1. **A real need.** It serves a need the specification leaves out.
2. **Nothing changes.** Every field, type and behavior the specification defines stays
   as defined.
3. **Additive and ignorable.** A client that does not know the addition still works,
   and a sender may leave it out.
4. **Specification types first.** It reuses the specification's types where they fit.
5. **Documented.** It is listed in `EXTENSIONS` in `openrois.interfaces.catalog`,
   says "OpenRoIS extension" in its description, and appears in §17.3.

The cross-check tests enforce the last test. With `OPENROIS_NORMATIVE_DIR` set, every
catalog, notification and profile model may carry only the fields of the IDL or the
XSD plus the registered extensions.

### 17.3 Extensions

| Extension | Where | Need it serves |
|-----------|-------|----------------|
| `component_profiles` | `rois.system.get_profile` result | A client learns what each component instance supports, including user-defined components with no published profile. The XSD engine profile names its components by ref only. The UML model links it to its component profiles by reference, and this map carries each referenced profile once, keyed by fully qualified ref. |
| `function` | `HRIComponentProfile` | The engine and clients know which components need a bind before commands. The values `actuation`, `sensing` and `function` are the RoSO classes that `OWL.ttl` assigns to the basic components (§11). |
| `results` | `rois.event.notify_event` params | The event payload. Without it, every event costs a `get_event_detail` round trip. `get_event_detail` still returns the payload until the event expires. |
| `rois.system.profile_changed` | Notification with no params | The specification gives a client no way to learn that components joined or left, other than polling `get_profile`. |

### 17.4 Conditions

The IDL types `Condition_t` as a string that carries an ISO 19143 filter expression.
OpenRoIS keeps it a string and writes it in a subset of CQL2-Text, the text encoding of
the OGC Common Query Language (OGC 21-065r2), which grew out of the OGC filter
encoding that ISO 19143 is based on:

```
condition   = [ comparison *( "AND" comparison ) ]
comparison  = property ( "=" / "LIKE" ) literal
```

- An empty condition is no filter. A literal is single-quoted, with a single quote
  inside it written twice. In a `LIKE` pattern, `%` matches any run of characters and
  `_` matches one.
- Two properties select components: `component_ref`, the fully qualified ref, and
  `component_type`, the URN of the component profile identifier, for example
  `urn:x-rois:def:component:OMG::PersonDetection`. They apply to `search`,
  `bind_any`, `get_profile`, `query` and `subscribe`.
- `query` and `subscribe` go to the one component that declares the query or event
  type and matches the condition, for example `component_ref = 'reachy_real/head'`.
  When no component matches, the engine returns `UNSUPPORTED`. When several match, it
  returns `BAD_PARAMETER`.
- No property is defined yet for the result filters of `get_error_detail`,
  `get_command_result` and `get_event_detail`, so those conditions must be empty.
- An engine answers a condition it cannot parse, or a property the method does not
  support, with `BAD_PARAMETER`.

`openrois.interfaces.condition` parses, matches and builds conditions.

### 17.5 Profiles and Refs

- Every `component_ref` is fully qualified as `engine_id/ref`, for example
  `reachy_real/head`.
- The `identifier` of a component profile is the component type, for example
  authority `OMG` and code `PersonDetection`. Two instances of one type share it and
  differ by ref.
- An engine profile's `component_ids` lists every component reachable through that
  engine, including those of its child engines, which `sub_profiles` also list.
- The interfaces packages hold the full profile of each basic component type they model
  as a constant, for example `NAVIGATION_PROFILE`: the XML profile with the messages of
  the RoIS_Common profile it includes, listed first, and the RoSO function of the type.
  A component declares the constant of its type and implements a part of it. Its profile
  in `get_profile` lists only the messages it implements, so a client never sees an
  operation the component does not answer. `ROIS_COMMON_PROFILE`,
  `NAVIGATION_PROFILE`, `PERSON_DETECTION_PROFILE`, `REACTION_PROFILE` and
  `SYSTEM_INFORMATION_PROFILE` exist so far. `openrois.interfaces.components` defines
  them, and `interfaces/schema/profiles.json` carries them to the TypeScript package.
- The XSD types `HRIComponent` as `xsd:ID`: a name without `/` that appears once per
  document. Fully qualified refs contain `/`, and a parent profile repeats the refs of
  its sub profiles. Neither matters in the JSON form, where a ref is a plain string. An
  XML rendering of an OpenRoIS profile would have to encode the refs and list each
  component once.

### 17.6 Values

The IDL types the value of a `Result`, a `Parameter` and an `Argument` as `any`, and names
its type in `data_type_ref`. OpenRoIS carries every value as a string, written by its type:

| `data_type_ref` | String form | Example |
|-----------------|-------------|---------|
| `int`, `integer`, `long`, `short` | Decimal | `42` |
| `float`, `double` | A decimal number | `1.5` |
| `bool`, `boolean` | `true` or `false` | `true` |
| `Component_Status` | The enumerator name (§16, item 7) | `READY` |
| `string`, `RoISIdentifier`, `DateTime` and any other type | The text itself, ISO 8601 for `DateTime` | `kitchen` |
| `<type>[]` | A JSON array of the item type: numbers, `true` or `false`, or strings | `["kitchen", "hall"]` |

Type names match without regard to case, so `String[]` and `string[]` are one type. An
engine refuses a parameter value that does not fit its type with `BAD_PARAMETER`.
`openrois.interfaces.values` writes and reads these forms.

### 17.7 Commands, Ids and Status

- `execute` runs its items in order. It waits each item's `delay_time` before the item
  starts, and runs the commands of a `ConcurrentCommands` item at the same time.
- Every command completes exactly once, with one `rois.command.completed` notification
  to the client that sent it. `get_command_result` reads its results afterwards.
- A command that ends with a status other than `OK` stops the sequence. The commands of
  the later items complete with `ABORT` and never run, so a step that depends on an
  earlier one does not run after it failed.
- An engine refuses a `command_id` it already tracks with `BAD_PARAMETER`.
- The ids an engine assigns, for subscriptions, events, errors and `set_parameter`
  commands, start with the id of that engine, like refs: `reachy_real/sub-1`. They stay
  the same through every gateway above that engine, never collide across engines, and
  tell a service application or an agent which engine an id belongs to. Clients treat
  them as opaque strings.
- An engine answers `component_status` for each component whose profile includes it. A
  component is `UNINITIALIZED` until it is ready to take commands, `ERROR` when it could
  not start, `BUSY` while one of its commands runs, and `READY` otherwise.

---

*This reference is a non-normative summary. For the milestone roadmap, see
[roadmap.md](roadmap.md). For authoritative requirements, consult the
official OMG specification at <https://www.omg.org/spec/RoIS/2.0> and the
machine-readable files at <https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>.*
