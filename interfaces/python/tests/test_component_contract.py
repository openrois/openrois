"""Tests for the ComponentContract protocol contract.

These tests verify that the ComponentContract Protocol is well-formed, can be
implemented by dummy classes, and rejects incomplete implementations. They also
verify that the contract module remains transport-neutral.
"""

from typing import Protocol

from openrois.interfaces.bus import (
    CommandRequest,
    ComponentContract,
    DiscoverRequest,
    DiscoverResponse,
    EventEnvelope,
    EventSink,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeId,
    SubscribeRequest,
    SubscribeResponse,
)
from openrois.interfaces.hri import ReturnCode

# ---------------------------------------------------------------------------
# Dummy implementations
# ---------------------------------------------------------------------------


class CompleteComponentContract:
    """A minimal valid ComponentContract implementation."""

    async def discover(self, request: DiscoverRequest) -> DiscoverResponse:
        return DiscoverResponse(component_ref_list=["dummy/pd"])

    async def invoke(self, request: CommandRequest) -> InvokeResponse:
        return InvokeResponse(command_id="cmd-dummy")

    async def query(self, request: QueryRequest) -> QueryResponse:
        return QueryResponse()

    async def subscribe(
        self,
        request: SubscribeRequest,
        sink: EventSink,
    ) -> SubscribeResponse:
        return SubscribeResponse(subscribe_id="sub-dummy")

    async def unsubscribe(self, subscribe_id: SubscribeId) -> ReturnCode:
        return ReturnCode.OK


class IncompleteComponentContract:
    """Missing invoke and subscribe — should fail protocol checks."""

    async def discover(self, request: DiscoverRequest) -> DiscoverResponse:
        return DiscoverResponse()

    async def query(self, request: QueryRequest) -> QueryResponse:
        return QueryResponse()


# ---------------------------------------------------------------------------
# Protocol compliance tests
# ---------------------------------------------------------------------------


class TestComponentContractProtocol:
    def test_complete_adapter_is_instance(self) -> None:
        adapter = CompleteComponentContract()
        assert isinstance(adapter, ComponentContract)

    def test_incomplete_adapter_is_not_instance(self) -> None:
        adapter = IncompleteComponentContract()
        assert not isinstance(adapter, ComponentContract)

    def test_protocol_is_runtime_checkable(self) -> None:
        # ComponentContract inherits from Protocol, which is runtime_checkable by default
        # for Protocol subclasses with only method signatures.
        assert issubclass(ComponentContract, Protocol)

    def test_complete_adapter_methods_are_callable(self) -> None:
        adapter = CompleteComponentContract()
        assert callable(adapter.discover)
        assert callable(adapter.invoke)
        assert callable(adapter.query)
        assert callable(adapter.subscribe)


# ---------------------------------------------------------------------------
# Transport-neutrality tests
# ---------------------------------------------------------------------------


class TestTransportNeutrality:
    def test_no_transport_imports_in_bus_module(self) -> None:
        """Verify the bus module does not import transport-specific libraries."""
        import ast

        import openrois.interfaces.bus as bus_module

        source = bus_module.__loader__.get_source(bus_module.__name__)  # type: ignore[union-attr]
        assert source is not None

        tree = ast.parse(source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name.split(".")[0].lower())
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.add(node.module.split(".")[0].lower())

        forbidden = {"rclpy", "grpc", "websockets", "socket", "paho", "mqtt"}
        found = forbidden & imported_names
        assert not found, f"Transport-specific imports found in bus.py: {found}"

    def test_component_contract_signature_has_no_transport_types(self) -> None:
        """ComponentContract methods only use types from openrois.interfaces.bus."""
        import inspect

        for name in ("discover", "invoke", "query", "subscribe"):
            sig = inspect.signature(getattr(ComponentContract, name))
            for param in sig.parameters.values():
                annotation = param.annotation
                assert "rclpy" not in str(annotation).lower()
                assert "dds" not in str(annotation).lower()
                assert "grpc" not in str(annotation).lower()
                assert "websockets" not in str(annotation).lower()


# ---------------------------------------------------------------------------
# EventSink shape tests
# ---------------------------------------------------------------------------


class TestEventSink:
    def test_async_function_is_valid_sink(self) -> None:
        async def sink(envelope: EventEnvelope) -> None:
            pass

        # The real check: a CompleteComponentContract accepts it as subscribe(sink=...)
        adapter = CompleteComponentContract()
        import inspect

        sig = inspect.signature(adapter.subscribe)
        sink_param = sig.parameters["sink"]
        # With PEP 695 type aliases, the annotation is a TypeAliasType object
        # whose str() is the alias name ("EventSink"). Expand it via __value__
        # to verify the underlying Callable type structure.
        annotation = sink_param.annotation
        if hasattr(annotation, "__value__"):
            annotation_str = str(annotation.__value__)
        else:
            annotation_str = str(annotation)
        assert "Callable" in annotation_str
        assert "EventEnvelope" in annotation_str
        assert "Awaitable" in annotation_str

    def test_event_sink_callback_receives_envelope(self) -> None:
        received: list[EventEnvelope] = []

        async def sink(envelope: EventEnvelope) -> None:
            received.append(envelope)

        envelope = EventEnvelope(event_id="evt", event_type="person_detected")
        # Simulate adapter invocation
        import asyncio

        asyncio.run(sink(envelope))
        assert len(received) == 1
        assert received[0].event_type == "person_detected"
