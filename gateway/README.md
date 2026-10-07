# openrois-gateway

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

The OpenRoIS gateway: the process that hosts the main RoIS HRI Engine and faces the network.

Adapters and lower gateways connect to it as child engines on the path `/adapter`. Service
applications connect as clients on any other path. The gateway discovers each child engine's
components, aggregates their profiles, holds the bindings, runs command sequences across
the child engines, and routes every RoIS call and every event to where it belongs. It composes
`Engine` and `WsServer` from [`openrois-engine`](../engine/README.md) into a process with
configuration, logging and a graceful stop.

## Install

Not published to PyPI yet. From a clone of the repository:

```bash
pip install -e ./interfaces/python -e ./engine -e ./gateway
```

## Run

```bash
openrois-gateway                      # listens on ws://127.0.0.1:8765
openrois-gateway --host 0.0.0.0 --port 9000
python -m openrois.gateway --config gateway.yaml
```

Ctrl+C or SIGTERM stops the gateway: it closes every connection with code 1001 and exits
with code 0.

The gateway does not authenticate its peers, so it binds loopback by default. Bind another
interface only on a network you trust.

## Docker

```bash
# From the repository root.
docker build -f gateway/Dockerfile -t openrois-gateway .
docker run --rm -p 127.0.0.1:8765:8765 openrois-gateway --log-level debug
```

Inside the container the gateway listens on every interface, so Docker can publish the port.
Publish it on `127.0.0.1` unless the network is trusted. Settings come from
`OPENROIS_GATEWAY_*` variables (`-e`) or flags after the image name.

[`compose.yaml`](../compose.yaml) at the repository root runs the gateway with the
[mock adapter](../examples/mock-adapter/README.md) behind it:

```bash
docker compose up --build
python gateway/scripts/smoke.py
```

The smoke script connects as a client and waits until the adapter's components appear. It
then reads the profile, runs the queries, reads a relayed event, drives the mock navigation
to a target from bind to `reached_target`, and checks that a method outside the catalog
gets `METHOD_NOT_FOUND`. It needs only the `websockets` package and exits with 0 when every
check passes.

## Configuration

Each source overrides the one before it: the defaults, a YAML file, the environment, and the
command-line flags.

| Setting | Flag | Environment | Default |
|---------|------|-------------|---------|
| Interface to bind | `--host` | `OPENROIS_GATEWAY_HOST` | `127.0.0.1` |
| TCP port, `0` for a free one | `--port` | `OPENROIS_GATEWAY_PORT` | `8765` |
| Engine id in the profile | `--engine-id` | `OPENROIS_GATEWAY_ENGINE_ID` | `gateway` |
| Log level: `debug`, `info`, `warning`, `error` | `--log-level` | `OPENROIS_GATEWAY_LOG_LEVEL` | `info` |
| Seconds to wait for a child engine's reply | `--child-timeout` | `OPENROIS_GATEWAY_CHILD_TIMEOUT` | `10` |
| YAML file with settings | `--config` | `OPENROIS_GATEWAY_CONFIG` | None |

The YAML file is a flat mapping with the setting names below. A key it does not know is an
error.

```yaml
host: 127.0.0.1
port: 8765
engine_id: gateway
log_level: info
child_timeout: 10
```

| Exit code | Meaning |
|-----------|---------|
| `0` | Stopped by a signal |
| `1` | The gateway could not start, for example because the port is taken |
| `2` | The configuration is invalid |

## Embed

```python
import asyncio

from openrois.gateway import Gateway, GatewayConfig


async def main() -> None:
    gateway = Gateway(GatewayConfig(port=0))
    stop = asyncio.Event()
    # run() serves until SIGTERM, SIGINT, or until the event is set.
    await gateway.run(stop)


asyncio.run(main())
```

`start()` and `stop()` are available on their own, and `port` reports the bound port.

## Test

```bash
pip install -e ./interfaces/python -e ./engine -e "./gateway[dev]"
cd gateway && pytest && mypy && ruff check src/ tests/ scripts/
```

## Status

Alpha, pre-1.0, unstable API. The gateway answers the RoIS method catalog that the
TypeScript SDK and the HRI client speak. Health endpoints and a compose healthcheck are
planned for [Phase 5](https://openrois.org/docs/project/roadmap).

## License

Apache-2.0.
