#!/usr/bin/env python3
"""RoIS client demo for the RealSense adapter.

Connects to the OpenRoIS gateway, discovers the three person
components (PersonDetection / PersonLocalization / PersonIdentification),
binds and starts them, subscribes to their events, and prints a live
summary:

  person_detected    - printed whenever the person count changes
  person_localized   - printed ~1/s while persons are visible
  person_identified  - printed whenever the tracking ID set changes
  event rates        - reported every 10 s

Usage:
    python demo_client.py [URL] [--duration SECONDS]

    URL         gateway WebSocket URL (default ws://127.0.0.1:8765)
    --duration  auto-exit after N seconds (default: run until Ctrl+C)

The engine_id is "realsense-1" (matches openrois-profile.yaml.example).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

import websockets

ENGINE = "realsense-1"
COMPONENTS = [
    ("PersonDetection", "person_detected"),
    ("PersonLocalization", "person_localized"),
    ("PersonIdentification", "person_identified"),
]


async def run(url: str, duration: float) -> None:
    print(f"connecting to {url} ...")
    async with websockets.connect(url) as ws:
        queued: list[dict] = []

        async def next_msg(timeout: float = 10.0) -> dict:
            return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))

        async def rpc(rid: str, method: str, params: dict) -> dict:
            """Send a JSON-RPC request and wait for its response.

            Event notifications that arrive while waiting are queued
            and processed later by the main loop.
            """
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
            }))
            while True:
                msg = await next_msg()
                if msg.get("id") == rid and "result" in msg:
                    return msg["result"]
                if "method" in msg:
                    queued.append(msg)

        # -- discover, bind, start, subscribe --
        r = await rpc("search", "rois.command.search", {})
        refs = r.get("component_ref_list", [])
        print("components:", refs)
        missing = [c for c, _ in COMPONENTS if f"{ENGINE}/{c}" not in refs]
        if missing:
            raise SystemExit(
                f"components not found: {missing} — is the adapter running?"
            )

        for i, (comp, event) in enumerate(COMPONENTS):
            full = f"{ENGINE}/{comp}"
            await rpc(f"b{i}", "rois.command.bind", {"component_ref": full})
            r = await rpc(f"x{i}", "rois.command.execute", {
                "component_ref": full, "command_type": "start", "parameters": [],
            })
            if r.get("return_code") != "OK":
                raise SystemExit(f"start failed for {full}: {r}")
            r = await rpc(f"s{i}", "rois.event.subscribe", {
                "component_ref": full, "event_type": event,
            })
            if r.get("return_code") != "OK":
                raise SystemExit(f"subscribe failed for {full}: {r}")

        print("subscribed: person_detected / person_localized / person_identified")
        print("waiting for events ... (Ctrl+C to stop)\n")

        loop = asyncio.get_running_loop()
        deadline = (loop.time() + duration) if duration > 0 else None

        counts = {ev: 0 for _, ev in COMPONENTS}
        total = 0
        last_number: str | None = None
        last_ids: list[str] | None = None
        last_pos_t = 0.0
        last_rate_t = loop.time()

        while True:
            if deadline is not None and loop.time() >= deadline:
                break
            try:
                remaining = (deadline - loop.time()) if deadline is not None else 10.0
                msg = queued.pop(0) if queued else await next_msg(max(remaining, 0.1))
            except asyncio.TimeoutError:
                continue

            if msg.get("method") != "rois.event.notify":
                continue
            params = msg["params"]
            et = params["event_type"]
            results = {x["name"]: x["value"] for x in params["results"]}
            counts[et] += 1
            total += 1
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")

            if et == "person_detected":
                n = results.get("number", "?")
                if n != last_number:
                    print(f"[{now}] person_detected    number={n}")
                    last_number = n
            elif et == "person_localized":
                positions = json.loads(results.get("positions", "[]"))
                if positions and loop.time() - last_pos_t >= 1.0:
                    p = positions[0]
                    extra = f" (+{len(positions) - 1})" if len(positions) > 1 else ""
                    print(f"[{now}] person_localized   id={p['id']} "
                          f"x={p['x']:+.2f} y={p['y']:+.2f} z={p['z']:+.2f} m{extra}")
                    last_pos_t = loop.time()
            else:
                ids = [i["id"] for i in json.loads(results.get("identifiers", "[]"))]
                if ids != last_ids:
                    print(f"[{now}] person_identified  ids={ids}")
                    last_ids = ids

            if loop.time() - last_rate_t >= 10.0:
                dt = loop.time() - last_rate_t
                rates = "  ".join(f"{ev}={counts[ev] / dt:.1f}Hz" for _, ev in COMPONENTS)
                print(f"--- rates: {rates} ---")
                counts = {ev: 0 for _, ev in COMPONENTS}
                last_rate_t = loop.time()

        print(f"\nreceived {total} events total — done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RoIS client demo for the RealSense adapter",
    )
    parser.add_argument("url", nargs="?", default="ws://127.0.0.1:8765",
                        help="gateway WebSocket URL (default: ws://127.0.0.1:8765)")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="auto-exit after N seconds (default: run until Ctrl+C)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url, args.duration))
    except KeyboardInterrupt:
        print("\nclient stopped")
    except (ConnectionRefusedError, OSError) as exc:
        raise SystemExit(f"cannot connect to {args.url} — is the gateway running? ({exc})")


if __name__ == "__main__":
    main()