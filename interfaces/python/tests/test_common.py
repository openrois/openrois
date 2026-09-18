"""Tests for openrois.interfaces.common — Common component types."""


from openrois.interfaces.common import (
    COMPONENT_STATUS_MAP,
    STREAM_STATUS_MAP,
    ComponentStatus,
    ComponentStatusT,
    StreamStatus,
    StreamStatusT,
)


class TestComponentStatus:
    def test_all_values(self) -> None:
        assert set(ComponentStatus) == {
            ComponentStatus.UNINITIALIZED,
            ComponentStatus.READY,
            ComponentStatus.BUSY,
            ComponentStatus.WARNING,
            ComponentStatus.ERROR,
        }

    def test_string_values(self) -> None:
        assert ComponentStatus.UNINITIALIZED.value == "UNINITIALIZED"
        assert ComponentStatus.READY.value == "READY"
        assert ComponentStatus.BUSY.value == "BUSY"
        assert ComponentStatus.WARNING.value == "WARNING"
        assert ComponentStatus.ERROR.value == "ERROR"

    def test_from_string(self) -> None:
        assert ComponentStatus("READY") is ComponentStatus.READY

    def test_is_str_enum(self) -> None:
        assert isinstance(ComponentStatus.READY, str)

    def test_numeric_mapping(self) -> None:
        assert COMPONENT_STATUS_MAP[ComponentStatus.UNINITIALIZED] == 0
        assert COMPONENT_STATUS_MAP[ComponentStatus.READY] == 1
        assert COMPONENT_STATUS_MAP[ComponentStatus.BUSY] == 2
        assert COMPONENT_STATUS_MAP[ComponentStatus.WARNING] == 3
        assert COMPONENT_STATUS_MAP[ComponentStatus.ERROR] == 4

    def test_numeric_type_alias(self) -> None:
        val: ComponentStatusT = 1
        assert isinstance(val, int)


class TestStreamStatus:
    def test_all_values(self) -> None:
        assert set(StreamStatus) == {
            StreamStatus.NOT_CONNECTED,
            StreamStatus.NOT_RUNNING,
            StreamStatus.RUNNING,
            StreamStatus.SUSPENDED,
            StreamStatus.RESUMED,
        }

    def test_string_values(self) -> None:
        # Values match the IDL enum names
        assert StreamStatus.NOT_CONNECTED.value == "STREAMING_NOT_CONNECTED"
        assert StreamStatus.NOT_RUNNING.value == "STREAMING_NOT_RUNNING"
        assert StreamStatus.RUNNING.value == "STREAMING_RUNNING"
        assert StreamStatus.SUSPENDED.value == "STREAMING_SUSPENDED"
        assert StreamStatus.RESUMED.value == "STREAMING_RESUMED"

    def test_from_string(self) -> None:
        assert StreamStatus("STREAMING_RUNNING") is StreamStatus.RUNNING

    def test_is_str_enum(self) -> None:
        assert isinstance(StreamStatus.RUNNING, str)

    def test_numeric_mapping(self) -> None:
        assert STREAM_STATUS_MAP[StreamStatus.NOT_CONNECTED] == 0
        assert STREAM_STATUS_MAP[StreamStatus.NOT_RUNNING] == 1
        assert STREAM_STATUS_MAP[StreamStatus.RUNNING] == 2
        assert STREAM_STATUS_MAP[StreamStatus.SUSPENDED] == 3
        assert STREAM_STATUS_MAP[StreamStatus.RESUMED] == 4

    def test_numeric_type_alias(self) -> None:
        val: StreamStatusT = 2
        assert isinstance(val, int)
