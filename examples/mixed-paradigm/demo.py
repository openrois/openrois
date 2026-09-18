"""One application, one gateway, a robot and a virtual agent.

Starts a gateway, connects the mock robot adapter (a simulated Kachaka-class
robot) and the avatar adapter (a text-based virtual agent) to it, then plays a
service application that:

1. discovers the components of both;
2. asks each SystemInformation for its position;
3. makes both say the same sentence through SpeechSynthesis, with identical
   calls, and waits for both completions.

The application addresses components by ref only. Nothing in its code depends
on which one is a robot and which one is an avatar.

Usage: python demo.py [--port 8765]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import websockets
from openrois_components_core import meta_from_decorators
from openrois_core import Engine, EventEmitter, WsClient, WsServer

EXAMPLES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXAMPLES / "mock-adapter"))
sys.path.insert(0, str(EXAMPLES / "avatar-adapter"))
import avatar_adapter  # noqa: E402
import mock_adapter  # noqa: E402

logger = logging.getLogger("demo")


class Application:
    """A service application speaking JSON-RPC to the gateway."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._next = 0
        self.notifications: list[dict[str, Any]] = []

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._next += 1
        await self._ws.send(json.dumps(
            {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params},
        ))
        while True:
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=10))
            if msg.get("id") == self._next:
                return dict(msg["result"])
            self.notifications.append(msg)

    async def wait_completed(self, command_id: str) -> str:
        """Block until rois.command.completed arrives for the command; return its status."""
        while True:
            for msg in list(self.notifications):
                if msg.get("method") == "rois.command.completed" \
                        and msg["params"].get("command_id") == command_id:
                    self.notifications.remove(msg)
                    return str(msg["params"]["status"])
            msg = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=10))
            self.notifications.append(msg)


def robot_engine() -> Engine:
    engine = Engine(engine_id="robot_1", platform="mock")
    for cls in mock_adapter.COMPONENT_CLASSES:
        meta = meta_from_decorators(cls)
        engine.register_component(meta.ref, cls({}), meta)
    return engine


def avatar_engine() -> Engine:
    profile = {"engine": {"id": "avatar_1", "platform": "avatar"}, "components": {}}
    return avatar_adapter.build_engine(profile)


async def run(port: int) -> dict[str, Any]:
    gateway = Engine(engine_id="gateway", enforce_bindings=True)
    server = WsServer(gateway)
    await server.start("127.0.0.1", port)
    port = server._server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"

    adapters = []
    for engine in (robot_engine(), avatar_engine()):
        engine.component_registry.set_emitter(EventEmitter(asyncio.get_running_loop()))
        adapters.append(asyncio.create_task(WsClient(engine, url)._run_async()))
    while len(gateway.get_sub_engines()) < 2:
        await asyncio.sleep(0.05)

    outcome: dict[str, Any] = {}
    async with websockets.connect(url) as ws:
        app = Application(ws)
        await app.call("rois.system.connect")

        # 1. Discover. The application sees refs, not paradigms.
        refs = (await app.call("rois.command.search"))["component_ref_list"]
        speakers = [r for r in refs if r.endswith("/SpeechSynthesis")]
        informers = [r for r in refs if r.endswith("/SystemInformation")]
        logger.info("Components: %s", ", ".join(refs))
        outcome["speakers"] = speakers

        # 2. Query both the same way.
        positions = {}
        for ref in informers:
            result = await app.call(
                "rois.query.query", component_ref=ref, query_type="robot_position",
            )
            positions[ref] = {r["name"]: r["value"] for r in result["results"]}
            logger.info("%s is at %s", ref, positions[ref])
        outcome["positions"] = positions

        # 3. Make both speak with identical calls, then wait for both completions.
        sentence = "Hello from OpenRoIS"
        commands: dict[str, str] = {}
        for ref in speakers:
            await app.call("rois.command.bind", component_ref=ref)
            await app.call(
                "rois.command.set_parameter", component_ref=ref,
                parameters=[{"name": "speech_text", "data_type_ref": "string", "value": sentence}],
            )
            executed = await app.call(
                "rois.command.execute", component_ref=ref, command_type="execute",
            )
            commands[ref] = executed["command_id"]
            logger.info("%s accepted %s", ref, executed["command_id"])
        statuses = {}
        for ref, command_id in commands.items():
            statuses[ref] = await app.wait_completed(command_id)
            logger.info("%s completed %s: %s", ref, command_id, statuses[ref])
            await app.call("rois.command.release", component_ref=ref)
        outcome["completions"] = statuses

    for task in adapters:
        task.cancel()
    for task in adapters:
        try:
            await task
        except asyncio.CancelledError:
            pass
    await server.stop()
    return outcome


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=0, help="gateway port (default: ephemeral)")
    args = parser.parse_args()
    outcome = asyncio.run(run(args.port))
    print(json.dumps(outcome, indent=2))
    return 0 if all(s == "OK" for s in outcome["completions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
