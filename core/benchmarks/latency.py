"""Control-plane latency of OpenRoIS.

Measures, over real WebSockets on the loopback interface:

- query and execute round trips from an application to an adapter, first through
  a gateway (application, gateway, adapter: three processes' worth of hops in one
  process) and then directly against the adapter's engine served on its own port;
- event delivery latency, from the component's emit to the application's receipt.

Usage: python benchmarks/latency.py [--iterations N] [--json]

The numbers describe the middleware overhead only. The fake components answer
immediately, so a real robot adds its own backend time on top.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from typing import Any

import websockets
from openrois.interfaces.bus import InvokeResponse
from openrois.interfaces.hri import Result, ReturnCode
from openrois_components_core import (
    component,
    invoke,
    meta_from_decorators,
    query,
    results,
    subscribe,
)

from openrois_core import Engine, EventEmitter, WsClient, WsServer


@component("Navigation", function="actuation")
class BenchNavigation:
    def __init__(self) -> None:
        self.pending: asyncio.Queue[float] = asyncio.Queue()

    @query("component_status")
    async def status(self) -> list[Result]:
        return results.status("READY")

    @invoke("execute")
    async def execute(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="cmd")

    @invoke("start")
    async def start(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("stop")
    async def stop(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("suspend")
    async def suspend(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @invoke("resume")
    async def resume(self, parameters: list[dict[str, Any]]) -> InvokeResponse:
        return InvokeResponse(return_code=ReturnCode.OK, command_id="")

    @subscribe("reached_target")
    async def on_reached(self) -> None:
        pass

    async def fire(self) -> None:
        # The event carries its emission time so the receiver can measure latency.
        await self.parent.emit_async(  # type: ignore[attr-defined]
            "Navigation", "reached_target",
            [Result(name="sent_at", data_type_ref="float", value=repr(time.perf_counter()))],
        )


class Application:
    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._next = 0

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._next += 1
        await self._ws.send(json.dumps(
            {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params},
        ))
        while True:
            msg = json.loads(await self._ws.recv())
            if msg.get("id") == self._next:
                return dict(msg["result"])

    async def next_event(self) -> dict[str, Any]:
        while True:
            msg = json.loads(await self._ws.recv())
            if msg.get("method") == "rois.event.notify":
                return dict(msg["params"])


def summarize(samples_s: list[float]) -> dict[str, float]:
    ms = sorted(s * 1000 for s in samples_s)
    return {
        "n": len(ms),
        "p50_ms": round(statistics.median(ms), 3),
        "p95_ms": round(ms[int(len(ms) * 0.95) - 1], 3),
        "p99_ms": round(ms[int(len(ms) * 0.99) - 1], 3),
        "max_ms": round(ms[-1], 3),
    }


async def time_calls(app: Application, method: str, n: int, **params: Any) -> list[float]:
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        result = await app.call(method, **params)
        samples.append(time.perf_counter() - t0)
        assert result["return_code"] == "OK", result
    return samples


async def time_events(app: Application, nav: BenchNavigation, n: int) -> list[float]:
    samples = []
    for _ in range(n):
        await nav.fire()
        params = await app.next_event()
        sent_at = float(next(r["value"] for r in params["results"] if r["name"] == "sent_at"))
        samples.append(time.perf_counter() - sent_at)
    return samples


async def measure(iterations: int) -> dict[str, Any]:
    # Adapter: an engine with the benchmark component, served directly on a port
    # (the "direct" path) and connected to a gateway (the "gateway" path).
    adapter_engine = Engine(engine_id="robot_1", platform="bench")
    adapter_engine.component_registry.set_emitter(EventEmitter(asyncio.get_running_loop()))
    nav = BenchNavigation()
    adapter_engine.register_component("Navigation", nav, meta_from_decorators(BenchNavigation))

    gateway = Engine(engine_id="gateway", enforce_bindings=True)
    gateway_server = WsServer(gateway)
    await gateway_server.start("127.0.0.1", 0)
    gateway_port = gateway_server._server.sockets[0].getsockname()[1]

    direct_server = WsServer(adapter_engine)
    await direct_server.start("127.0.0.1", 0)
    direct_port = direct_server._server.sockets[0].getsockname()[1]

    client = WsClient(adapter_engine, f"ws://127.0.0.1:{gateway_port}")
    adapter_task = asyncio.create_task(client._run_async())
    while not gateway.get_sub_engines():
        await asyncio.sleep(0.02)

    report: dict[str, Any] = {"iterations": iterations, "paths": {}}
    for label, port, ref in (
        ("gateway", gateway_port, "robot_1/Navigation"),
        ("direct", direct_port, "Navigation"),
    ):
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            app = Application(ws)
            await app.call("rois.system.connect")
            await time_calls(
                app, "rois.query.query", 50, component_ref=ref, query_type="component_status",
            )
            queries = await time_calls(
                app, "rois.query.query", iterations,
                component_ref=ref, query_type="component_status",
            )
            await app.call("rois.command.bind", component_ref=ref)
            executes = await time_calls(
                app, "rois.command.execute", iterations,
                component_ref=ref, command_type="execute",
            )
            sub = await app.call(
                "rois.event.subscribe", component_ref=ref, event_type="reached_target",
            )
            events = await time_events(app, nav, iterations)
            await app.call("rois.event.unsubscribe", subscribe_id=sub["subscribe_id"])
            report["paths"][label] = {
                "query": summarize(queries),
                "execute": summarize(executes),
                "event": summarize(events),
            }

    adapter_task.cancel()
    try:
        await adapter_task
    except asyncio.CancelledError:
        pass
    await direct_server.stop()
    await gateway_server.stop()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()
    report = asyncio.run(measure(args.iterations))
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        return 0
    print(f"{args.iterations} iterations per measurement, milliseconds\n")
    print(f"{'path':<8} {'operation':<9} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}")
    for path, ops in report["paths"].items():
        for op, s in ops.items():
            cells = " ".join(f"{s[k]:>8.3f}" for k in ("p50_ms", "p95_ms", "p99_ms", "max_ms"))
            print(f"{path:<8} {op:<9} {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
