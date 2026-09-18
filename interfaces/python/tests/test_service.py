"""Tests for openrois.interfaces.service — Service callback types."""

import pytest
from pydantic import ValidationError

from openrois.interfaces.service import (
    CompletedEvent,
    CompletedStatus,
    ErrorType,
    NotifyErrorEvent,
    NotifyEventPayload,
)


class TestCompletedStatus:
    def test_all_values(self) -> None:
        assert set(CompletedStatus) == {
            CompletedStatus.OK,
            CompletedStatus.ERROR,
            CompletedStatus.ABORT,
            CompletedStatus.OUT_OF_RESOURCES,
            CompletedStatus.TIMEOUT,
        }

    def test_string_values(self) -> None:
        assert CompletedStatus.OK.value == "OK"
        assert CompletedStatus.ABORT.value == "ABORT"

    def test_from_string(self) -> None:
        assert CompletedStatus("ABORT") is CompletedStatus.ABORT

    def test_is_str_enum(self) -> None:
        assert isinstance(CompletedStatus.OK, str)


class TestErrorType:
    def test_all_values(self) -> None:
        assert set(ErrorType) == {
            ErrorType.ENGINE_INTERNAL_ERROR,
            ErrorType.COMPONENT_INTERNAL_ERROR,
            ErrorType.COMPONENT_NOT_RESPONDING,
            ErrorType.USER_DEFINED_ERROR,
        }

    def test_string_values(self) -> None:
        assert ErrorType.ENGINE_INTERNAL_ERROR.value == "ENGINE_INTERNAL_ERROR"
        assert ErrorType.COMPONENT_NOT_RESPONDING.value == "COMPONENT_NOT_RESPONDING"

    def test_from_string(self) -> None:
        assert ErrorType("COMPONENT_INTERNAL_ERROR") is ErrorType.COMPONENT_INTERNAL_ERROR


class TestNotifyErrorEvent:
    def test_construction(self) -> None:
        event = NotifyErrorEvent(
            error_id="err-001",
            error_type=ErrorType.COMPONENT_INTERNAL_ERROR,
        )
        assert event.error_id == "err-001"
        assert event.error_type == ErrorType.COMPONENT_INTERNAL_ERROR

    def test_serialization(self) -> None:
        event = NotifyErrorEvent(
            error_id="err-001",
            error_type=ErrorType.COMPONENT_NOT_RESPONDING,
        )
        d = event.model_dump()
        assert d["error_id"] == "err-001"
        assert d["error_type"] == "COMPONENT_NOT_RESPONDING"

    def test_json_round_trip(self) -> None:
        event = NotifyErrorEvent(
            error_id="err-002",
            error_type=ErrorType.ENGINE_INTERNAL_ERROR,
        )
        j = event.model_dump_json()
        event2 = NotifyErrorEvent.model_validate_json(j)
        assert event == event2

    def test_frozen(self) -> None:
        event = NotifyErrorEvent(error_id="err-001", error_type=ErrorType.USER_DEFINED_ERROR)
        with pytest.raises(ValidationError):
            event.error_id = "changed"  # type: ignore[misc]


class TestCompletedEvent:
    def test_construction(self) -> None:
        event = CompletedEvent(
            command_id="cmd-001",
            status=CompletedStatus.OK,
        )
        assert event.command_id == "cmd-001"
        assert event.status == CompletedStatus.OK

    def test_serialization(self) -> None:
        event = CompletedEvent(command_id="cmd-001", status=CompletedStatus.ABORT)
        d = event.model_dump()
        assert d["command_id"] == "cmd-001"
        assert d["status"] == "ABORT"

    def test_json_round_trip(self) -> None:
        event = CompletedEvent(command_id="cmd-001", status=CompletedStatus.TIMEOUT)
        j = event.model_dump_json()
        event2 = CompletedEvent.model_validate_json(j)
        assert event == event2


class TestNotifyEventPayload:
    def test_construction(self) -> None:
        payload = NotifyEventPayload(
            event_id="evt-001",
            event_type="person_detected",
            subscribe_id="sub-001",
            expire="2025-01-15T11:00:00Z",
        )
        assert payload.event_id == "evt-001"
        assert payload.event_type == "person_detected"
        assert payload.subscribe_id == "sub-001"
        assert payload.expire == "2025-01-15T11:00:00Z"

    def test_default_expire(self) -> None:
        payload = NotifyEventPayload(
            event_id="evt-001",
            event_type="face_detected",
            subscribe_id="sub-001",
        )
        assert payload.expire == ""

    def test_json_round_trip(self) -> None:
        payload = NotifyEventPayload(
            event_id="evt-001",
            event_type="person_detected",
            subscribe_id="sub-001",
            expire="2025-01-15T11:00:00Z",
        )
        j = payload.model_dump_json()
        payload2 = NotifyEventPayload.model_validate_json(j)
        assert payload == payload2
