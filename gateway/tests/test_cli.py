"""The openrois-gateway command: exit codes, and a graceful stop on a signal."""

from __future__ import annotations

import asyncio
import re
import signal
import socket
import sys

import pytest
from websockets.asyncio.client import connect

from openrois.gateway import main


def test_version_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("openrois-gateway ")


def test_an_invalid_configuration_exits_with_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--port", "70000"]) == 2
    assert "port: Input should be less than or equal to 65535" in capsys.readouterr().err


def test_a_taken_port_exits_with_1() -> None:
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert main(["--port", str(port)]) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
async def test_a_signal_stops_the_process_gracefully(stop_signal: signal.Signals) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "openrois.gateway",
        "--port",
        "0",
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stderr is not None
    try:
        port = await asyncio.wait_for(_listening_port(process.stderr), timeout=10.0)
        async with connect(f"ws://127.0.0.1:{port}") as client:
            process.send_signal(stop_signal)
            assert await asyncio.wait_for(process.wait(), timeout=5.0) == 0
            await asyncio.wait_for(client.wait_closed(), timeout=2.0)
            assert client.close_code == 1001
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _listening_port(stderr: asyncio.StreamReader) -> int:
    """Read the gateway's log until it reports the port it listens on."""
    pattern = re.compile(rb"Listening on ws://[^:]+:(\d+)")
    while True:
        line = await stderr.readline()
        if not line:
            raise AssertionError("The gateway exited before it listened.")
        match = pattern.search(line)
        if match:
            return int(match.group(1))
