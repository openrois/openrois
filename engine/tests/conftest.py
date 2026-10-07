"""Fixtures for the engine tests. The helpers they build on are in _support.py."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from openrois.engine import Engine, WsServer
from tests._support import CHILD_TIMEOUT, Adapter, Gateway, RpcClient, start_adapter


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    engine = Engine(engine_id="gateway", enforce_bindings=True)
    server = WsServer(engine, child_timeout=CHILD_TIMEOUT)
    await server.start("127.0.0.1", 0)
    try:
        yield Gateway(engine, server)
    finally:
        await server.stop()


@pytest.fixture
async def client(gateway: Gateway) -> AsyncIterator[RpcClient]:
    rpc = await RpcClient.connect(gateway.url)
    try:
        yield rpc
    finally:
        await rpc.close()


@pytest.fixture
async def adapter(gateway: Gateway) -> AsyncIterator[Adapter]:
    started = await start_adapter(gateway)
    try:
        yield started
    finally:
        await started.stop()
