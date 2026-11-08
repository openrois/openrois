"""Wait for the mock adapter to reach the gateway before the integration tests run."""

from __future__ import annotations

import asyncio
import os

import pytest
from openrois.sdk import RoISClient, TransportError

URL = os.environ.get("OPENROIS_GATEWAY_URL", "")


async def _ready(timeout: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            async with RoISClient.connect(URL, connect_timeout=2.0) as client:
                if "mock/navigation" in await client.search():
                    return True
        except (TransportError, OSError):
            pass
        await asyncio.sleep(1.0)
    return False


@pytest.fixture(scope="session", autouse=True)
def gateway_ready() -> None:
    """Fail early with a clear message when the stack is not up."""
    if not URL:
        return
    if not asyncio.run(_ready(90.0)):
        pytest.fail(f"No mock/navigation at {URL} after 90 s. Is the compose stack up?")
