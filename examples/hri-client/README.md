# hri-client

Generic RoIS HRI Client: a browser-based component inspector for any RoIS engine.

## What This Is

A web application that connects to any RoIS HRI Engine over WebSocket, fetches
the engine profile via `rois.system.get_profile`, and renders a dynamic UI panel
for each discovered component. The user can run queries, execute commands, and
subscribe to events without knowing anything about the specific robot or engine.

## Install

```bash
cd examples/hri-client
npm install
```

## Run

```bash
npm run dev
```

Open the browser, enter the engine WebSocket URL (default `ws://localhost:8765`),
and click Connect.

## Use with the mock engine

```bash
# Terminal 1: start the mock engine
cd examples/mock-engine
npm start

# Terminal 2: start the hri-client
cd examples/hri-client
npm run dev
```

Open the browser and connect to `ws://localhost:8765`.

## Use with a real engine

Point the hri-client at the engine's WebSocket URL. The engine must implement
`rois.system.get_profile` and return `component_profiles` in the response for
the client to render component panels.

## Architecture

The hri-client is the client-side reference implementation in the OpenRoIS
examples:

| Example | RoIS role |
|---|---|
| `mock-adapter` | BusAdapter (robot-side) |
| `adapter-template` | BusAdapter (robot-side) |
| `mock-engine` | HRI Engine (server-side) |
| `hri-client` | HRI Client (client-side) |

The app uses `@openrois/sdk` (`RoISClient`) for the WebSocket transport and
JSON-RPC protocol. It is robot-agnostic: no hardcoded component refs, query
types, or map data.