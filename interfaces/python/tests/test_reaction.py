"""Tests for openrois.interfaces.components.reaction — Reaction typed models."""

import pytest

from openrois.interfaces.common import ComponentStatus
from openrois.interfaces.components.reaction import (
    REACTION_URN,
    ReactionGetParameterResult,
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionStatusResult,
)


class TestReactionURN:
    def test_urn_value(self) -> None:
        assert REACTION_URN == "urn:x-rois:def:component:OMG::Reaction"


class TestReactionSetParameter:
    def test_construction_single(self) -> None:
        cmd = ReactionSetParameter(reaction_ref=["wave"])
        assert cmd.reaction_ref == ["wave"]

    def test_construction_multiple(self) -> None:
        cmd = ReactionSetParameter(reaction_ref=["wave", "smile", "nod"])
        assert len(cmd.reaction_ref) == 3
        assert cmd.reaction_ref[1] == "smile"

    def test_serialization(self) -> None:
        cmd = ReactionSetParameter(reaction_ref=["led_green"])
        d = cmd.model_dump()
        assert d["reaction_ref"] == ["led_green"]

    def test_json_round_trip(self) -> None:
        cmd = ReactionSetParameter(reaction_ref=["wave", "nod"])
        j = cmd.model_dump_json()
        cmd2 = ReactionSetParameter.model_validate_json(j)
        assert cmd == cmd2

    def test_extra_forbidden(self) -> None:
        with pytest.raises(Exception):
            ReactionSetParameter(reaction_ref=["wave"], extra_field="bad")  # type: ignore[call-arg]


class TestReactionSetParameterResult:
    def test_construction(self) -> None:
        result = ReactionSetParameterResult(command_id="cmd-react-001")
        assert result.command_id == "cmd-react-001"

    def test_frozen(self) -> None:
        result = ReactionSetParameterResult(command_id="cmd-react-001")
        with pytest.raises(Exception):
            result.command_id = "changed"  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        result = ReactionSetParameterResult(command_id="cmd-react-002")
        j = result.model_dump_json()
        result2 = ReactionSetParameterResult.model_validate_json(j)
        assert result == result2


class TestReactionGetParameterResult:
    def test_construction(self) -> None:
        result = ReactionGetParameterResult(
            available_reactions=["wave", "nod", "smile"],
            reaction_ref="wave",
        )
        assert result.available_reactions == ["wave", "nod", "smile"]
        assert result.reaction_ref == "wave"

    def test_empty_available_reactions(self) -> None:
        result = ReactionGetParameterResult(
            available_reactions=[],
            reaction_ref="",
        )
        assert result.available_reactions == []
        assert result.reaction_ref == ""

    def test_json_round_trip(self) -> None:
        result = ReactionGetParameterResult(
            available_reactions=["wave", "bow"],
            reaction_ref="bow",
        )
        j = result.model_dump_json()
        result2 = ReactionGetParameterResult.model_validate_json(j)
        assert result == result2

    def test_frozen(self) -> None:
        result = ReactionGetParameterResult(
            available_reactions=["wave"],
            reaction_ref="wave",
        )
        with pytest.raises(Exception):
            result.reaction_ref = "nod"  # type: ignore[misc]


class TestReactionStatusResult:
    def test_construction_ready(self) -> None:
        result = ReactionStatusResult(status=ComponentStatus.READY)
        assert result.status == ComponentStatus.READY

    def test_construction_busy(self) -> None:
        result = ReactionStatusResult(status=ComponentStatus.BUSY)
        assert result.status == ComponentStatus.BUSY

    def test_serialization(self) -> None:
        result = ReactionStatusResult(status=ComponentStatus.ERROR)
        d = result.model_dump()
        assert d["status"] == "ERROR"

    def test_json_round_trip(self) -> None:
        result = ReactionStatusResult(status=ComponentStatus.WARNING)
        j = result.model_dump_json()
        result2 = ReactionStatusResult.model_validate_json(j)
        assert result == result2

    def test_frozen(self) -> None:
        result = ReactionStatusResult(status=ComponentStatus.READY)
        with pytest.raises(Exception):
            result.status = ComponentStatus.BUSY  # type: ignore[misc]