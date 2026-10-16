# Robotic Interaction Service (RoIS) Framework - Reference

> An in-depth reference for the OMG **Robotic Interaction Service (RoIS) Framework**, Version 2.0.
>
> - **OMG Document Number:** formal/26-06-03 (June 2026)
> - **Normative reference:** <https://www.omg.org/spec/RoIS/2.0>
> - **Machine-readable files:** <https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>,
>   the 20250801 set at <https://www.omg.org/spec/RoIS/20250801/>
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

Clause 2 of the specification states what an implementation claiming conformance
shall do:

- Provide the interfaces described in **§8.2 RoIS Interface**.
- Support the message data structures described in **§8.3 RoIS Profiles**.
- Support the **Common Messages** of **§8.4** *for the basic components it
  implements* (it need not implement every basic component).
- Handle component profiles described as **XML files** (the XML-Profile PSM
  machine-readable files) and the messages defined therein.

**OpenRoIS makes no conformance claim.** It implements the interfaces of §8.2, the
profiles of §8.3 and the common messages of §8.4 (conformance points CP1 to CP3), as
§16 records them, and it reads and writes the XML profiles. A claim waits until all
four points are closed, and the engine does not yet load XML-declared profiles at run
time. §17 describes how OpenRoIS implements what the specification leaves to the
platform.

---

## 4. Core Concepts & Terminology

| Term | Meaning |
|------|---------|
| **HRI** | Human-Robot Interaction. |
| **HRI Component** | An abstract object that uses sensors/actuators to provide a specific HRI function (person detection, speech, etc.). Internal structure is encapsulated. |
| **Basic HRI Component** | An HRI Component providing a *commonly implemented* HRI function. Table 8-36 lists 17, each with an XML profile, although the terms of clause 4 still say 15. |
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
`UNSUPPORTED` is in the IDL but not in the specification's return code table (§16,
item 5).

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
   engine assigns a `command_id` to every command and returns it (§16, item 1). The
   operation runs
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
`STREAMING_SUSPENDED`, `STREAMING_RESUMED`. OpenRoIS serves streaming through the two
streaming components instead (§17.1).

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

The specification text and its machine-readable files disagree in places. When they
do, OpenRoIS applies one order of precedence: the XML profiles and `XML-Profiles.xsd`
decide the wire, the specification text decides behavior, the IDL fills gaps, and the
hpp headers break ties. Every exception OpenRoIS makes is an entry below, and nowhere
else. Each entry gives what the specification says, what the files say, and what
OpenRoIS does.

The sources are formal/26-06-03 and the 20250801 machine-readable set. The entries
come from the October 2026 validation table, which checked every normative file
against the 2.0-beta2 document. They keep that table's row numbers (V1 to V36) and its
2.0-beta2 figure and table numbers. formal/26-06-03 writes the numbers with a hyphen
(Table 8-15), and entries F1 and F2 cite it directly. With `OPENROIS_NORMATIVE_DIR`
set, `interfaces/python/tests/_normative_expectations.py` checks the files against
these entries.

1. **`execute` returns the command ids** (V1; Figures 8.5 and 8.10, Table 8.3;
   `RoIS_HRI.idl`).
   Spec: `execute` takes `command_unit_list` as inout, and the engine assigns a
   `command_id` to every command it receives.
   Files: the IDL declares the list `in` only, and the XSD requires a `command_id` on
   every command message.
   OpenRoIS: the engine assigns every id and returns the list with the ids filled in,
   as `ExecuteResult.command_unit_list` (§17.3). That field realizes the inout of
   Figure 8.5.

2. **`ConcurrentCommands` and branches** (V3, F2; Figure 8.11, Tables 8.15 and 8.16,
   Annex B.1, and Table 8-15 of formal/26-06-03; `XML-Profiles.xsd`).
   Spec: `ConcurrentCommands` holds a `branch_list` of `Branch`, each a sequential
   `command_list`. formal/26-06-03 renames the attribute `command list` in Table 8-15
   but still types it `Branch`, and keeps `branch_list` in Annex B.1.
   Files: `ConcurrentCommandsType` holds a `command_list` of `CommandMessageType`, and
   `BranchType` is declared but never used.
   OpenRoIS: runs the branches in parallel and each branch in order, and reads a flat
   `command_list` as one-command branches. The codec reads both forms and writes the
   XSD form. Its tests use the complete Annex B.1 example of 2.0-beta2, because the
   formal example stops after the first branch.

3. **Arguments on queries and events** (V9; Table 8.56, Figure 8.28;
   `AudioStreaming.xml`, `VideoStreaming.xml`, `XML-Profiles.xsd`).
   Spec: `notify_stream_status` lists `stream_id`, `timestamp` and `status` as its
   arguments.
   Files: the streaming profiles put `stream_id` under `Arguments` of a query and an
   event, and the XSD declares `Arguments` on command message profiles only.
   OpenRoIS: query and event profiles carry an arguments list. The condition of a
   query or a subscription gives the argument values (§17.9).

4. **`get_stream_status`** (V8; Table 8.6 against Table 8.56, Figures 8.9 and 8.28;
   `AudioStreaming.xml`).
   Spec: Table 8.6 names the query `query_stream_status`, while Table 8.56 and both
   figures name it `get_stream_status`.
   Files: `get_stream_status`.
   OpenRoIS: `get_stream_status`.

5. **The `UNSUPPORTED` return code** (Table 8-1 of formal/26-06-03; `RoIS_HRI.idl`).
   Spec: Table 8-1 lists five return codes and has no `UNSUPPORTED`.
   Files: the IDL `ReturnCode_t` has six values, including `UNSUPPORTED`.
   OpenRoIS: returns `UNSUPPORTED` for an operation a component does not offer, such
   as an unknown command type or a query that no component serves.

6. **Several sub-component profiles** (V4; Figure 8.12, Table 8.34;
   `XML-Profiles.xsd`).
   Spec: `sub_component` is 0..1, and "only one item may be defined".
   Files: `SubComponentProfile` is 0..unbounded. Every standard profile except
   SystemInformation and RoISCommon itself names RoISCommon and nothing else.
   OpenRoIS: the reader accepts several, and the writer emits what the component
   declares.

7. **`Component_Status` and `Component_Status_t`** (`RoISCommon.xml`,
   `SystemInformation.xml`, `RoIS_Common.idl`, `RoIS_Common.hpp`).
   Spec: the result of `component_status` is a `Component_Status` enumeration.
   Files: the XML profiles and the hpp use the enumeration. The IDL declares
   `out Component_Status_t status` with `typedef long Component_Status_t`, a number.
   OpenRoIS: a status travels as the enumerator name, for example `READY`.

8. **`HRIComponent` in an engine profile** (V6; Annex A.4; `XML-Profiles.xsd`).
   Spec: the values are URNs such as
   `urn:x-rois:def:HRIComponent:ATR::PersonDetection`.
   Files: `HRIComponent` is typed `xsd:ID`, which forbids colons and must be unique in
   the document, so the specification's own engine profile example does not validate.
   OpenRoIS: treats `HRIComponent` as a plain string and does not run full XSD
   validation on engine profiles.

9. **Type codes** (V7, V33; Annex A, Annex B.2; all 18 profiles).
   Spec: `data_type_ref` codes are URNs such as `urn:x-rois:def:DataType:ATR::Integer`.
   Files: short codes in twelve spellings, ten once case is ignored: `string`,
   `String`, `int`, `bool`, `string[]`, `String[]`, `int[]`, `RoISIdentifier`,
   `RoISIdentifier[]`, `DateTime`, `Component_Status` and `Stream_Status`.
   OpenRoIS: keeps the codes verbatim, maps these to value forms (§17.6) without regard
   to case, and passes unknown codes through as strings.

10. **Every profile has the same `gml:id`** (V34; Annex A.3; all 18 profiles).
    Spec: one profile per document, each with its own `gml:id`.
    Files: every file uses `gml:id="component_profile"`.
    OpenRoIS: the engine profile writer gives every embedded component profile a unique
    `gml:id`.

11. **The 20250801 file set and the 20240801 namespace** (F1; formal/26-06-03;
    `https://www.omg.org/spec/RoIS/20250801/`).
    Spec: the machine-readable files are published under
    `https://www.omg.org/spec/RoIS/20250801/`.
    Files: every profile, and the `targetNamespace` of `XML-Profiles.xsd`, still
    declare `http://www.omg.org/spec/RoIS/20240801`.
    OpenRoIS: reads `http://www.omg.org/spec/RoIS/20250801` as an alias of the
    `20240801` namespace, and writes `20240801`.

12. **The FaceLocalization namespace** (V36; Annex A; `FaceLocalization.xml`).
    Spec: every profile is in the namespace `http://www.omg.org/spec/RoIS/20240801`.
    Files: `FaceLocalization.xml` declares that namespace with a trailing space, which
    a strict XML parser rejects as an invalid URI.
    OpenRoIS: strips the surrounding whitespace from the namespace URI before parsing.

13. **SystemInformation** (V20; Table 8.41, Figure 8.13; `SystemInformation.xml`,
    `RoIS_System_Information.idl`).
    Spec: SystemInformation has no RoIS_Common messages, and `engine_status` returns
    the status and the operable time as a List<DateTime>.
    Files: the XML profile includes no RoISCommon and types `operable_time` as a
    single `DateTime`. The IDL derives its `Query` from `RoIS_Common::Query` and keeps
    the list.
    OpenRoIS: no `component_status` and no RoIS_Common commands on SystemInformation,
    and a single `DateTime` on the wire.

14. **Navigation parameters and event** (V13; Table 8.53, Figure 8.25;
    `Navigation.xml`, `RoIS_Navigation.idl`).
    Spec: `target_position` List<Data> [RLS], mandatory, and `time_limit`
    UnlimitedNatural, optional. There is no event.
    Files: `target_positions` `string[]`, `time_limit` `int` with default `0`, and a
    `reached_target` event with the results `target` and `is_final_target`. The IDL
    spells the parameter `target_position` and its `Event` interface is empty.
    OpenRoIS: `target_positions` as a list of strings carrying the RLS data, and the
    `reached_target` event.

15. **Localization defaults and position data** (V22; Tables 8.43, 8.46 and 8.48; the
    three localization profiles).
    Spec: the detection threshold and the minimum interval are optional, and the
    position data is List<Data> [RLS].
    Files: `position_data` is typed `String[]`, and both parameters carry
    `default_value=""` on an `int`.
    OpenRoIS: an empty `default_value` means no default, and RLS data travels as
    strings.

16. **SpeechRecognition names** (V24; Table 8.49, Figure 8.21;
    `SpeechRecognition.xml`, `RoIS_Speech_Recognition.idl`).
    Spec: `set_parameter` takes `languages`, `grammer` and `rule`, and `get_parameter`
    also returns the recognizable languages.
    Files: the parameters `rule`, `languages` (default `"jp"`) and `grammar`, and a
    `recognizable_languages` query.
    OpenRoIS: the XML names. The default `"jp"` is not an ISO 639-1 code, and the
    profile keeps it verbatim without validation.

17. **`recognizable_gestures` is read-only** (V25; Table 8.50, Figure 8.22;
    `GestureRecognition.xml`).
    Spec: `recognizable_gestures` comes from `get_parameter` only, and there is no
    `set_parameter`.
    Files: `recognizable_gestures` is a ParameterProfile, which reads as settable.
    OpenRoIS: a read-only parameter (§17.3), and `set_parameter` on it answers
    `BAD_PARAMETER`. The same rule applies to `available_encodings` and
    `available_transports` of the streaming components.

18. **Reaction `reaction_ref`** (V26; Table 8.52, Figure 8.24; `Reaction.xml`,
    `RoIS_Reaction.idl`).
    Spec: `set_parameter` takes a single reaction ref, and `get_parameter` returns
    `available_reactions` and the reaction ref.
    Files: the XML has `reaction_ref` as the only parameter, a single `RoISIdentifier`,
    and `available_reactions` as a query. The IDL takes a list of refs in
    `set_parameter`.
    OpenRoIS: a single `reaction_ref`, and the `available_reactions` query.

19. **SpeechSynthesis voices and languages** (V11; Table 8.51, Figure 8.23;
    `SpeechSynthesis.xml`, `RoIS_Speech_Synthesis.idl`).
    Spec: `get_parameter` also returns `synthesizable_languages` and
    `synthesizable_characters`, and `character` is a RoIS_Identifier.
    Files: the XML has two queries, `synthesizable_languages` (result `languages`) and
    `available_voices` (result `characters`), types `character` as a `string` and
    spells `ssml_text`. The IDL spells `SSML_text`.
    OpenRoIS: the XML profile. `get_parameter` returns the five parameters, and the
    lists come from the two queries.

20. **The ontology parent of the streaming components** (V35; Table 8.40 and the
    Table 8-39 IRIs; `OWL.ttl`).
    Spec: AudioStreaming and VideoStreaming sit under Function, and the other basic
    components under Sensing or Actuation.
    Files: `OWL.ttl` places the streaming types under
    `https://www.omg.org/spec/RoSO/RoboticServiceOntology/Function`, while Sensing and
    Actuation are in `https://www.omg.org/spec/RoSO/RoboticServiceFunctionOntology/`, a
    different namespace.
    OpenRoIS: the profile generator reads the function from `OWL.ttl` alone and matches
    both namespaces. The streaming components are Function, and the function sets the
    bind cardinality (§17.8).

21. **Command-result, event-detail and error-detail profiles** (Figure 8.12;
    `XML-Profiles.xsd`, all 18 profiles).
    Spec: Figure 8.12 draws profile types for command results, event details and error
    details.
    Files: neither the XSD nor any profile file defines them.
    OpenRoIS: follows the XSD and does not model them. `get_command_result`,
    `get_event_detail` and `get_error_detail` return plain result lists (§17.10).

22. **Withdrawn: `set_parameter` performs the action** (Tables 8.3, 8.14, 8.37 and 8.51
    to 8.55, Annex B.2, §8.2.2.5).
    Spec: the tables of the actuation components read as if a component acts "by
    specifying" its parameters, with `set_parameter` as its only command method. Table
    8.3 says `set_parameter` "sets parameters of the bound HRI Component", Table 8.14
    makes a `set_parameter` command message operate like that operation, and Table 8.37
    gives `start` "start the functionality of the HRI Component".
    Files: every standard profile but SystemInformation includes RoISCommon, with
    `start`, `stop`, `suspend` and `resume`, beside the component's own parameters.
    OpenRoIS: an October 9 ruling that `set_parameter` performs the action was withdrawn
    on October 15. `set_parameter` configures the component and completes when the
    values apply. `start` runs the functionality with the values the component holds,
    and completes when that run ends for an actuation component, or once it runs for a
    sensing one. `stop` ends it and aborts a running action.

---

## 17. How OpenRoIS Implements RoIS

This section describes OpenRoIS, not the specification. It records the choices
OpenRoIS makes where the specification leaves them to the platform-specific model, and
the few places where it adds to the specification. The interfaces packages
(`interfaces/`) define all of it, and the Python engine, the gateway, the component SDK
and the TypeScript SDK implement it.

### 17.1 Wire Binding

RoIS defines operations, not a transport (§6.2). OpenRoIS carries them as JSON-RPC 2.0
messages, over WebSocket between processes.

- Each operation of the System, Command, Query and Event interfaces is a JSON-RPC
  method named `rois.<interface>.<operation>`, with `system`, `command`, `query` and
  `event` as the interface names, for example `rois.command.bind_any`.
- Streaming has no interface of its own. AudioStreaming and VideoStreaming are ordinary
  components with the RoSO function `function`, and their stream status comes through
  the `get_stream_status` query and the `notify_stream_status` event. An engine answers
  any `rois.stream.*` method with the JSON-RPC error `METHOD_NOT_FOUND`.
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
| `command_unit_list` | `rois.command.execute` result | The client learns the ids the engine assigned (§17.7), to match each `completed` notification and read results. It realizes the inout `command_unit_list` that Figure 8.5 draws (§16, item 1). |
| `component_profiles` | `rois.system.get_profile` result | A client learns what each component instance supports, including user-defined components with no published profile. The XSD engine profile names its components by ref only. The UML model links it to its component profiles by reference, and this map carries each referenced profile once, keyed by fully qualified ref. |
| `function` | `HRIComponentProfile` | The engine and clients know which components need a bind before commands. The values `actuation`, `sensing` and `function` are the RoSO classes that `OWL.ttl` assigns to the basic components (§11). |
| `read_only` | `ParameterProfile` | The specification lists some parameters under `get_parameter` only, but the XML profiles declare them as ParameterProfiles, which reads as settable. The engine refuses `set_parameter` on them with `BAD_PARAMETER` (§16, item 17). |
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
- The Python and TypeScript interfaces packages hold the full profile of each of the 18
  standard profiles as a constant, for example `NAVIGATION_PROFILE`: the XML profile
  with the messages of the RoIS_Common profile it includes, listed first, and the RoSO
  function of the type. A component declares the constant of its type and implements a
  part of it. Its profile in `get_profile` lists only the messages it implements, so a
  client never sees an operation the component does not answer. The constants are
  generated from the XML profiles and `OWL.ttl`. `openrois.interfaces.components`
  defines them, and `interfaces/schema/profiles.json` carries them to the TypeScript
  package.
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

- **Ids.** The engine assigns the id of every command it receives, as
  `engine_id/cmd-N`, and returns the sequence with the ids filled in
  (`ExecuteResult.command_unit_list`, §16 item 1). An id a client sends is ignored. A
  trusted parent engine, such as a gateway forwarding to its adapter, names the ids
  itself, and the child engine reuses them. From a parent, a missing, repeated or
  already tracked id answers `BAD_PARAMETER`.
- **Other engine ids.** The ids an engine assigns for subscriptions, events, errors and
  `set_parameter` commands also start with the engine id, like refs:
  `reachy_real/sub-1`. They stay the same through every gateway above that engine and
  never collide across engines. Clients treat them as opaque strings.
- **Checks before anything runs.** `execute` answers `UNSUPPORTED` for a command type
  the component does not offer, `ERROR` when the session has not bound every
  component the sequence names (§17.8), and `BAD_PARAMETER` for an empty sequence or
  arguments that do not fit the profile. Nothing in a refused sequence runs.
- **Order and branches.** `execute` runs its items in order and waits each item's
  `delay_time` before the item starts. The branches of a `ConcurrentCommands` item
  run in parallel and each branch runs in order. A flat `command_list` is one branch
  per command (§16 item 2). An engine that forwards a command to a child engine waits
  the delay itself, so the delay counts once.
- **Failure.** A command that ends with a status other than `OK` stops the rest of its
  branch and every later item: those commands complete with `ABORT` and never run.
  The other branches of the same item run to their end.
- **Completion.** Every command completes exactly once, with one
  `rois.command.completed` notification to the session that sent it.
  `get_command_result` reads its results afterwards.
- **Timeout.** The `timeout` of a command message profile, in milliseconds, judges only
  whether the command started, counted from its receipt (Table 8.21). A command that
  started runs for as long as its handler does. One that has not started when the
  timeout elapses, because it waits behind another command, a suspension or a child
  engine, completes with `TIMEOUT`.
- **`set_parameter`.** The engine checks and applies the values before it replies, then
  replies `OK` with an engine-assigned `command_id`, and `rois.command.completed`
  follows the reply. An unknown parameter, a read-only one (§17.3), a value that does
  not fit its type, or values the component's hook refuses answer `BAD_PARAMETER`
  with no command id, and the old values stay. Inside `execute`, the same checks
  refuse the sequence with `BAD_PARAMETER`, and a hook refusal ends that command with
  `ERROR`.
- **RoIS_Common.** Every component whose profile includes RoISCommon serves `start`,
  `stop`, `suspend` and `resume` without handlers. A component is started from the
  moment a start begins until `stop`, or until that start ends other than `OK`. A
  `start` without a handler completes `OK` at once. On a component that is not started,
  `suspend`, `resume` and `stop` complete `OK` and run no handler. `suspend` holds the
  component's later commands, which wait without starting until `resume` or time out,
  while `set_parameter` still applies and the component's events are dropped. `stop`
  ends the suspension, and the held commands complete with `ABORT`. A component that
  serves RoISCommon therefore never answers `UNSUPPORTED` to these four, and it
  overrides any of them when its function needs more. An override adds to this
  default: a suspend handler runs after the hold, a resume handler before the release.
  A suspend whose handler fails lifts its hold. `component_status` does not change
  while a component is suspended, since Table 8.38 has no suspended state.
- **`component_status`.** The answer is for the asking session. A component is
  `UNINITIALIZED` until its resources are open, `ERROR` when they could not open, and
  `BUSY` when another session holds its actuation bind (§17.8). A raised status
  outranks the lifecycle, `ERROR` above `WARNING` above `UNINITIALIZED`. Otherwise the
  component is `READY`, also while its commands run. A shared component is never
  `BUSY` through binds.

### 17.8 Sessions and Binds

- **Connect gating.** Every request before `rois.system.connect`, and after
  `rois.system.disconnect`, answers `ERROR`. That includes requests from a trusted
  parent engine. A gateway connects to each child engine before it reads its profile.
- **Binds on every component.** `get_parameter`, `set_parameter` and `execute` need a
  bind on every component they name, through `bind` or `bind_any`. The gateway checks
  the binds for its child engines too.
- **Cardinality by RoSO function.** The `function` of a component profile (§17.3)
  sets how many sessions may hold it. An `actuation` component takes one bind at a
  time, so a bind from another session answers `OUT_OF_RESOURCES`. A `sensing` or
  `function` component, and a component with no function, takes one bind per session,
  shared by every session. Binding again from the holder is `OK`. `bind_any` reserves
  a component the session can bind under these rules.
- **`release`.** It drops the caller's bind and aborts the caller's commands on that
  component, which complete with `ABORT`, so the next session cannot take an actuator
  mid-motion. Other sessions' binds and commands on a shared component are untouched.
- **`disconnect`.** It releases the session's binds, ends its subscriptions and aborts
  its sequences. A running command ends at once with its backend halted, and later
  items never run.
- **Through a gateway.** The gateway checks its clients' binds itself and reaches each
  child engine through a trusted session, which the child does not check again. That
  session holds one bind in the child for all the gateway's clients, so the gateway
  applies these rules itself. When a client's command in a child is aborted and that
  client was the last one holding the component, the gateway sends the child `stop`,
  when the profile declares it, and then `release`. On a shared
  component with other holders, the gateway only stops waiting for that command, and
  the command runs on in the child.

### 17.9 Events

- `subscribe` from a session that already holds a subscription with the same event
  type and condition returns that subscription's id. Another session gets its own id.
  `unsubscribe` of an unknown or removed id answers `OK`.
- `rois.event.notify_event` carries the event's results (§17.3), and
  `get_event_detail` returns them until the event expires.
- **Arguments.** A query or an event profile may declare arguments (§16 item 3). A
  query takes their values from `=` comparisons in its condition, for example
  `stream_id = 'a1'`. A property that is neither a component property (§17.4) nor an
  argument, or a `LIKE` on an argument, answers `BAD_PARAMETER`.
- **Filtering.** A subscription whose condition names argument values receives only
  the events that concern those values. A subscription without them receives every
  event of its type, and an event that concerns no particular value reaches every
  subscription.

### 17.10 Errors

- **Raising.** A component, a resource or the engine raises `WARNING` or `ERROR` with a
  message, and clears it when the cause is gone. A raise that changes what the
  component reports sends `rois.system.notify_error`. A raise that changes nothing,
  and clearing, send nothing.
- **Error types.** The `error_type` is one of the specification's:
  `ENGINE_INTERNAL_ERROR`, `COMPONENT_INTERNAL_ERROR`, `COMPONENT_NOT_RESPONDING` and
  `USER_DEFINED_ERROR`.
- **Who is told.** A component's error goes to the sessions that hold a bind on it or a
  subscription to it, and to the trusted parent engine, with the `error_type`
  `COMPONENT_INTERNAL_ERROR`. A resource's error is one error per component that uses
  it, with `COMPONENT_NOT_RESPONDING`. An engine's error goes to every connected
  session, with `ENGINE_INTERNAL_ERROR`. Through a gateway, an adapter's errors reach
  the gateway's clients the same way.
- **Detail.** The `error_id` is `engine_id/err-N`. `get_error_detail` returns the
  `component_ref`, the `status`, the `message` and the `time` until the status is
  cleared, and `BAD_PARAMETER` after.
- **Effect.** While a component has `ERROR` raised, its commands complete with `ERROR`
  without running, its queries answer `ERROR`, and its events are held back.


---

*This reference is a non-normative summary. For the milestone roadmap, see
[roadmap.md](roadmap.md). For authoritative requirements, consult the
official OMG specification at <https://www.omg.org/spec/RoIS/2.0> and the
machine-readable files at <https://www.omg.org/spec/RoIS/2.0#docs-normative-machine>.*
