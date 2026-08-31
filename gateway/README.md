# @openrois/gateway

OpenRoIS Gateway process. Hosts the recursive Engine and exposes it over
WebSocket. This is the TypeScript proof of concept. The target is a Python
`openrois_core` package (see roadmap Phase 4).

## What This Is

The gateway is the only internet-facing process. It composes two functional
units:

- **Engine**: manages child engines (sub-engines), routes RoIS JSON-RPC calls,
  aggregates profiles, tracks bind/release.
- **WsServer**: WebSocket server, accepts client and adapter connections,
  relays events.

## Run

```bash
npm install
npm start
```

The gateway listens on `ws://0.0.0.0:8765` by default. Override with
`ENGINE_HOST` and `ENGINE_PORT` environment variables.

## Docker

```bash
docker compose up
```

See `docker-compose.yaml` at the repo root.