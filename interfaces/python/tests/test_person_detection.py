"""Tests for openrois.interfaces.components.person_detection — PersonDetection typed models."""

import pytest

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.person_detection import (
    PERSON_DETECTION_URN,
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)


class TestPersonDetectionURN:
    def test_urn_value(self) -> None:
        assert PERSON_DETECTION_URN == "urn:x-rois:def:component:OMG::PersonDetection"


class TestPersonDetectedEvent:
    def test_construction(self) -> None:
        event = PersonDetectedEvent(
            timestamp="2025-01-15T10:30:00Z",
            number=3,
        )
        assert event.timestamp == "2025-01-15T10:30:00Z"
        assert event.number == 3

    def test_serialization(self) -> None:
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=1)
        d = event.model_dump()
        assert d == {
            "timestamp": "2025-01-15T10:30:00Z",
            "number": 1,
        }

    def test_json_round_trip(self) -> None:
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=5)
        j = event.model_dump_json()
        event2 = PersonDetectedEvent.model_validate_json(j)
        assert event == event2

    def test_frozen(self) -> None:
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=2)
        with pytest.raises(Exception):
            event.number = 10  # type: ignore[misc]

    def test_zero_persons(self) -> None:
        """Edge case: zero persons detected."""
        event = PersonDetectedEvent(timestamp="2025-01-15T10:30:00Z", number=0)
        assert event.number == 0


class TestPersonDetectionStatusResult:
    def test_construction(self) -> None:
        result = PersonDetectionStatusResult(status=ComponentStatus.READY)
        assert result.status == ComponentStatus.READY

    def test_serialization(self) -> None:
        result = PersonDetectionStatusResult(status=ComponentStatus.BUSY)
        d = result.model_dump()
        assert d["status"] == "BUSY"

    def test_json_round_trip(self) -> None:
        result = PersonDetectionStatusResult(status=ComponentStatus.ERROR)
        j = result.model_dump_json()
        result2 = PersonDetectionStatusResult.model_validate_json(j)
        assert result == result2
