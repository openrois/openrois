"""The gateway process: serve() listens, answers, and stops cleanly."""

from __future__ import annotations

import asyncio
import json

import websockets

from openrois_core.gateway import build_parser, serve


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert (args.host, args.port) == ("0.0.0.0", 8765)
    assert (args.engine_id, args.log_level) == ("gateway", "INFO")


async def test_serve_answers_and_stops() -> None:
    stop = asyncio.Event()
    port = 18765
    task = asyncio.create_task(serve("127.0.0.1", port, engine_id="test-gateway", stop=stop))
    for _ in range(50):
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps(
                    {"jsonrpc": "2.0", "id": 1, "method": "rois.system.get_profile", "params": {}},
                ))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert reply["result"]["profile"]["identifier"]["code"] == "test-gateway"
                break
        except OSError:
            await asyncio.sleep(0.05)
    else:
        raise AssertionError("gateway never came up")
    stop.set()
    await asyncio.wait_for(task, timeout=5)
