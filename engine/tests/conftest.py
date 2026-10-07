"""Fixtures for the engine tests. The helpers they build on are in _support.py."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from tests._support import Adapter, Gateway, RpcClient, start_adapter


@pytest.fixture
async def gateway() -> AsyncIterator[Gateway]:
    running = await Gateway.start()
    try:
        yield running
    finally:
        await running.stop()


@pytest.fixture
async def client(gateway: Gateway) -> AsyncIterator[RpcClient]:
    rpc = await RpcClient.connect(gateway.url)
    try:
        yield rpc
    finally:
        await rpc.close()


@pytest.fixture
async def adapter(gateway: Gateway) -> AsyncIterator[Adapter]:
    started = await start_adapter(gateway.url, gateway)
    try:
        yield started
    finally:
        await started.stop()
