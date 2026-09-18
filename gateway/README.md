# @openrois/gateway

The TypeScript proof of concept of the OpenRoIS gateway: it hosts the recursive
engine and exposes it over WebSocket. It is superseded by the Python `openrois-core`
package in `core/` and is retired at the end of roadmap Phase 4. Keep it only for
reference.

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