"""The gateway process: serve() listens, answers, and stops cleanly."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import websockets

from openrois_core.gateway import ConfigError, build_parser, load_config, parse_args, serve


def test_parser_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROIS_PORT", raising=False)
    args = build_parser().parse_args([])
    assert (args.host, args.port) == ("0.0.0.0", 8765)
    assert (args.engine_id, args.log_level) == ("gateway", "INFO")
    assert args.auth_key is None and args.tls_cert is None


def test_config_file_supplies_defaults_and_the_command_line_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "gateway.yaml"
    config.write_text(
        "host: 127.0.0.1\nport: 9000\nengine_id: lab\n"
        "auth:\n  key: secret\n  issuer: lab-issuer\ntls:\n  cert: c.pem\n  key: k.pem\n",
    )
    monkeypatch.delenv("OPENROIS_PORT", raising=False)
    args = parse_args(["--config", str(config), "--port", "9001"])
    assert (args.host, args.port, args.engine_id) == ("127.0.0.1", 9001, "lab")
    assert (args.auth_key, args.auth_issuer) == ("secret", "lab-issuer")
    assert args.auth_algorithm == "HS256"
    assert (args.tls_cert, args.tls_key) == ("c.pem", "k.pem")

    # The environment sits between the command line and the file.
    monkeypatch.setenv("OPENROIS_PORT", "9002")
    monkeypatch.setenv("OPENROIS_GATEWAY_CONFIG", str(config))
    args = parse_args([])
    assert (args.port, args.engine_id) == (9002, "lab")


def test_config_file_rejects_unknown_keys(tmp_path: Path) -> None:
    config = tmp_path / "gateway.yaml"
    config.write_text("prot: 1\n")
    with pytest.raises(ConfigError, match="unknown option"):
        load_config(config)
    config.write_text("- not a mapping\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(config)


async def test_health_endpoint_answers_plain_http() -> None:
    stop = asyncio.Event()
    port = 18766
    task = asyncio.create_task(serve("127.0.0.1", port, engine_id="probe", stop=stop))
    body = None
    for _ in range(50):
        try:
            with await asyncio.to_thread(
                urllib.request.urlopen, f"http://127.0.0.1:{port}/health", timeout=5,
            ) as response:
                assert response.headers["Content-Type"] == "application/json"
                body = json.loads(response.read())
            break
        except urllib.error.HTTPError:
            raise
        except OSError:
            await asyncio.sleep(0.05)
    assert body == {
        "status": "ok", "engine_id": "probe", "adapters": 0, "clients": 0,
        "auth": False, "tls": False,
    }
    stop.set()
    await asyncio.wait_for(task, timeout=5)


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
