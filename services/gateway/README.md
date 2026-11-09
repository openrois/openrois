# openrois-gateway

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)

The OpenRoIS gateway: the process that hosts the main RoIS HRI Engine and faces the network.

Adapters and lower gateways connect to it as child engines on the path `/adapter`. Service
applications connect as clients on any other path. The gateway discovers each child engine's
components, aggregates their profiles, holds the bindings, runs command sequences across
the child engines, and routes every RoIS call and every event to where it belongs. It composes
`Engine` and `WsServer` from [`openrois-engine`](https://github.com/openrois/openrois/blob/dev/engine/README.md) into a process with
configuration, logging and a graceful stop.

## Install

```bash
pip install openrois-gateway
```

The gateway needs Python 3.12 or later. With [uv](https://docs.astral.sh/uv/), which fetches
Python itself, it runs with no install:

```bash
uvx --python 3.12 --from openrois-gateway openrois-gateway
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
interface only on a network you trust, and the gateway logs a warning when you do. Phones
and headsets need this, since they cannot reach a gateway on loopback.

## Docker

```bash
# From the repository root.
docker build -f services/gateway/Dockerfile -t openrois-gateway .
docker run --rm -p 127.0.0.1:8765:8765 openrois-gateway --log-level debug
```

Inside the container the gateway listens on every interface, so Docker can publish the port.
Publish it on `127.0.0.1` unless the network is trusted. Settings come from
`OPENROIS_GATEWAY_*` variables (`-e`) or flags after the image name.

[`compose.yaml`](https://github.com/openrois/openrois/blob/dev/compose.yaml) at the repository root runs the gateway with the
[mock adapter](https://github.com/openrois/openrois/blob/dev/testing/mock-adapter/README.md) behind it:

```bash
docker compose up --build
python testing/conformance/wire_check.py
```

The check connects as a client, waits until the adapter's components appear, and runs the
[conformance list](https://github.com/openrois/openrois/blob/dev/testing/conformance/README.md). It needs only the `websockets`
package and exits with 0 when every scenario passes.

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
pip install -e "./services/gateway[dev]"
cd services/gateway && pytest && mypy && ruff check src/ tests/
```

## Status

Alpha, pre-1.0, unstable API. The gateway answers the RoIS method catalog that the
JavaScript SDK and the OpenRoIS Inspector speak, with the RoIS behavior of CP1 to CP3 that
[`openrois-engine`](https://github.com/openrois/openrois/blob/dev/engine/README.md) implements, and makes no conformance claim.
Authentication is planned for `v0.3`, so the gateway binds to loopback by default. Health endpoints and a compose healthcheck are
next on the [roadmap](https://github.com/openrois/openrois/blob/dev/docs/roadmap.md).

## License

Apache-2.0.
