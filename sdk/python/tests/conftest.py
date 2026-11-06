"""What more than one test file needs."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPTED_SERVER = Path(__file__).parents[3] / "testing" / "conformance" / "scripted_server.py"


@pytest.fixture(scope="session")
def scripted_url() -> Iterator[str]:
    """The URL of a scripted server, which takes a path that picks its script."""
    with subprocess.Popen(
        [sys.executable, str(SCRIPTED_SERVER)], stdout=subprocess.PIPE, text=True
    ) as process:
        assert process.stdout is not None
        try:
            yield f"ws://127.0.0.1:{int(process.stdout.readline())}"
        finally:
            process.terminate()
