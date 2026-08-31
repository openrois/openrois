"""Tests for openrois.interfaces.bus — ComponentContract request/response/event models."""

import pytest
from pydantic import ValidationError

from openrois.interfaces.bus import (
    BusAdapterError,
    CommandRequest,
    ComponentNotFoundError,
    DiscoverRequest,
    DiscoverResponse,
    EventEnvelope,
    InvokeResponse,
    QueryRequest,
    QueryResponse,
    SubscribeRequest,
    SubscribeResponse,
)
from openrois.interfaces.common import StreamStatus
from openrois.interfaces.components.navigation import NavigationSetParameter
from openrois.interfaces.components.person_detection import PersonDetectedEvent
from openrois.interfaces.hri import Argument, CommandUnit, CommandUnitSequence, Parameter, Result, ReturnCode
from openrois.interfaces.service import CompletedStatus, ErrorType

# ---------------------------------------------------------------------------
# DiscoverRequest / DiscoverResponse
# ---------------------------------------------------------------------------


class TestDiscoverRequest:
    def test_default_condition(self) -> None:
        req = DiscoverRequest()
        assert req.condition == ""

    def test_with_condition(self) -> None:
        req = DiscoverRequest(condition="component_type='FaceDetection'")
        assert req.condition == "component_type='FaceDetection'"

    def test_frozen(self) -> None:
        req = DiscoverRequest()
        with pytest.raises(ValidationError):
            req.condition = "x"  # type: ignore[misc]


class TestDiscoverResponse:
    def test_default(self) -> None:
        resp = DiscoverResponse()
        assert resp.return_code == ReturnCode.OK
        assert resp.component_ref_list == []

    def test_with_refs(self) -> None:
        resp = DiscoverResponse(
            return_code=ReturnCode.OK,
            component_ref_list=["robot-a1/pd", "robot-a1/nav"],
        )
        assert resp.component_ref_list == ["robot-a1/pd", "robot-a1/nav"]

    def test_json_round_trip(self) -> None:
        resp = DiscoverResponse(component_ref_list=["r/pd"])
        j = resp.model_dump_json()
        resp2 = DiscoverResponse.model_validate_json(j)
        assert resp == resp2


# ---------------------------------------------------------------------------
# CommandRequest / InvokeResponse
# ---------------------------------------------------------------------------


class TestCommandRequest:
    def test_start_command(self) -> None:
        req = CommandRequest(
            component_ref="robot-a1/pd",
            command_type="start",
            command_id="cmd-001",
        )
        assert req.component_ref == "robot-a1/pd"
        assert req.command_type == "start"
        assert req.arguments == []
        assert req.parameters == []
        assert req.command_unit_sequence is None

    def test_set_parameter_with_arguments(self) -> None:
        req = CommandRequest(
            component_ref="robot-a1/navigation",
            command_type="set_parameter",
            command_id="cmd-002",
            arguments=[
                Argument(name="target_position", data_type_ref="string[]", value="1.0,2.0"),
            ],
        )
        assert len(req.arguments) == 1
        assert req.arguments[0].name == "target_position"

    def test_set_parameter_with_parameters(self) -> None:
        """CommandRequest.parameters accepts Parameter instances (IDL ParameterList)."""
        req = CommandRequest(
            component_ref="robot-a1/navigation",
            command_type="set_parameter",
            command_id="cmd-002b",
            parameters=[
                Parameter(name="time_limit", data_type_ref="int", value="30"),
                Parameter(name="routing_policy", data_type_ref="string", value="distance"),
            ],
        )
        assert len(req.parameters) == 2
        assert req.parameters[0].name == "time_limit"
        assert req.parameters[1].value == "distance"

    def test_parameters_json_round_trip(self) -> None:
        """Parameters round-trip through JSON as Parameter values."""
        req = CommandRequest(
            component_ref="robot-a1/nav",
            command_type="set_parameter",
            command_id="cmd-002c",
            parameters=[
                Parameter(name="target_positions", data_type_ref="string[]", value="1.0,2.0"),
            ],
        )
        j = req.model_dump_json()
        req2 = CommandRequest.model_validate_json(j)
        assert req == req2
        assert req2.parameters[0].name == "target_positions"

    def test_execute_with_sequence(self) -> None:

        seq = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(
                    component_ref="robot-a1/pd",
                    command_type="start",
                    command_id="c1",
                ),
            ],
        )
        req = CommandRequest(
            component_ref="robot-a1/pd",
            command_type="execute",
            command_id="cmd-003",
            command_unit_sequence=seq,
        )
        assert req.command_unit_sequence is not None
        assert len(req.command_unit_sequence.command_unit_list) == 1

    def test_json_round_trip(self) -> None:
        req = CommandRequest(
            component_ref="robot-a1/nav",
            command_type="start",
            command_id="cmd-004",
        )
        j = req.model_dump_json()
        req2 = CommandRequest.model_validate_json(j)
        assert req == req2


class TestInvokeResponse:
    def test_default(self) -> None:
        resp = InvokeResponse()
        assert resp.return_code == ReturnCode.OK
        assert resp.command_id == ""
        assert resp.results == []

    def test_with_command_id(self) -> None:
        resp = InvokeResponse(command_id="cmd-005")
        assert resp.command_id == "cmd-005"

    def test_with_results(self) -> None:
        resp = InvokeResponse(
            results=[Result(name="status", data_type_ref="Component_Status", value="READY")],
        )
        assert len(resp.results) == 1


# ---------------------------------------------------------------------------
# QueryRequest / QueryResponse
# ---------------------------------------------------------------------------


class TestQueryRequest:
    def test_component_status(self) -> None:
        req = QueryRequest(
            component_ref="robot-a1/pd",
            query_type="component_status",
        )
        assert req.component_ref == "robot-a1/pd"
        assert req.query_type == "component_status"
        assert req.condition == ""

    def test_with_condition(self) -> None:
        req = QueryRequest(
            component_ref="robot-a1/nav",
            query_type="robot_position",
            condition="robot_id='robot-a1'",
        )
        assert req.condition == "robot_id='robot-a1'"


class TestQueryResponse:
    def test_default(self) -> None:
        resp = QueryResponse()
        assert resp.return_code == ReturnCode.OK
        assert resp.results == []

    def test_with_results(self) -> None:
        resp = QueryResponse(
            return_code=ReturnCode.OK,
            results=[
                Result(name="status", data_type_ref="Component_Status", value="BUSY"),
            ],
        )
        assert resp.results[0].value == "BUSY"


# ---------------------------------------------------------------------------
# SubscribeRequest / SubscribeResponse
# ---------------------------------------------------------------------------


class TestSubscribeRequest:
    def test_person_detected(self) -> None:
        req = SubscribeRequest(
            component_ref="robot-a1/pd",
            event_type="person_detected",
        )
        assert req.event_type == "person_detected"
        assert req.condition == ""


class TestSubscribeResponse:
    def test_default(self) -> None:
        resp = SubscribeResponse()
        assert resp.return_code == ReturnCode.OK
        assert resp.subscribe_id == ""

    def test_with_subscribe_id(self) -> None:
        resp = SubscribeResponse(subscribe_id="sub-001")
        assert resp.subscribe_id == "sub-001"


# ---------------------------------------------------------------------------
# EventEnvelope
# ---------------------------------------------------------------------------


class TestEventEnvelope:
    def test_component_event(self) -> None:
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=3)
        envelope = EventEnvelope(
            event_id="evt-001",
            event_type="person_detected",
            subscribe_id="sub-001",
            component_ref="robot-a1/pd",
            payload=[
                Result(name="timestamp", data_type_ref="DateTime", value=event.timestamp),
                Result(name="number", data_type_ref="int", value=str(event.number)),
            ],
        )
        assert envelope.event_type == "person_detected"
        assert len(envelope.payload) == 2

    def test_completed_event(self) -> None:
        envelope = EventEnvelope(
            event_id="evt-002",
            event_type="completed",
            subscribe_id="sub-002",
            component_ref="robot-a1/nav",
            completed_status=CompletedStatus.OK,
        )
        assert envelope.completed_status == CompletedStatus.OK

    def test_error_event(self) -> None:
        envelope = EventEnvelope(
            event_id="evt-003",
            event_type="notify_error",
            component_ref="robot-a1/pd",
            error_type=ErrorType.COMPONENT_NOT_RESPONDING,
        )
        assert envelope.error_type == ErrorType.COMPONENT_NOT_RESPONDING

    def test_stream_status_event(self) -> None:
        envelope = EventEnvelope(
            event_id="evt-004",
            event_type="notify_stream_status",
            component_ref="robot-a1/video",
            stream_status=StreamStatus.RUNNING,
        )
        assert envelope.stream_status == StreamStatus.RUNNING

    def test_json_round_trip(self) -> None:
        envelope = EventEnvelope(
            event_id="evt-005",
            event_type="person_detected",
            subscribe_id="sub-003",
            component_ref="robot-a1/pd",
            payload=[
                Result(name="number", data_type_ref="int", value="2"),
            ],
        )
        j = envelope.model_dump_json()
        envelope2 = EventEnvelope.model_validate_json(j)
        assert envelope == envelope2

    def test_frozen(self) -> None:
        envelope = EventEnvelope(event_id="evt", event_type="x")
        with pytest.raises(ValidationError):
            envelope.event_type = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Typed component payload serialization
# ---------------------------------------------------------------------------


class TestTypedPayloadMapping:
    def test_navigation_set_parameter_to_command_request(self) -> None:
        """A typed Navigation command serializes into a generic CommandRequest."""
        typed = NavigationSetParameter(target_positions=["1.0,2.0,0.0"], time_limit=30)
        req = CommandRequest(
            component_ref="robot-a1/nav",
            command_type="set_parameter",
            command_id="cmd-nav-001",
            arguments=[
                Argument(
                    name="target_positions",
                    data_type_ref="string[]",
                    value=typed.target_positions[0],
                ),
                Argument(
                    name="time_limit",
                    data_type_ref="int",
                    value=str(typed.time_limit),
                ),
                Argument(
                    name="routing_policy",
                    data_type_ref="string",
                    value=typed.routing_policy,
                ),
            ],
        )
        assert req.arguments[0].value == "1.0,2.0,0.0"
        assert req.arguments[1].value == "30"

    def test_person_detected_to_event_envelope(self) -> None:
        """A typed PersonDetected event serializes into a generic EventEnvelope."""
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=5)
        envelope = EventEnvelope(
            event_id="evt-pd-001",
            event_type="person_detected",
            subscribe_id="sub-pd",
            component_ref="robot-a1/pd",
            payload=[
                Result(name="timestamp", data_type_ref="DateTime", value=event.timestamp),
                Result(name="number", data_type_ref="int", value=str(event.number)),
            ],
        )
        assert envelope.payload[1].value == "5"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestBusAdapterError:
    def test_default_return_code(self) -> None:
        err = BusAdapterError("something went wrong")
        assert err.message == "something went wrong"
        assert err.return_code == ReturnCode.ERROR

    def test_custom_return_code(self) -> None:
        err = BusAdapterError("not supported", return_code=ReturnCode.UNSUPPORTED)
        assert err.return_code == ReturnCode.UNSUPPORTED


class TestComponentNotFoundError:
    def test_fields(self) -> None:
        err = ComponentNotFoundError("robot-a1/unknown")
        assert err.component_ref == "robot-a1/unknown"
        assert err.return_code == ReturnCode.UNSUPPORTED
        assert "robot-a1/unknown" in str(err)
