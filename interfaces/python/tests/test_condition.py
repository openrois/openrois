"""Tests for the CQL2-Text subset of conditions (condition.py)."""

from __future__ import annotations

import pytest

from openrois.interfaces import condition as cond
from openrois.interfaces.condition import (
    COMPONENT_REF,
    COMPONENT_TYPE,
    Comparison,
    Condition,
    ConditionError,
    component_type_urn,
    parse_condition,
)
from openrois.interfaces.profiles import RoISIdentifierType

HEAD = {
    COMPONENT_REF: "reachy_real/head",
    COMPONENT_TYPE: "urn:x-rois:def:component:OpenRoIS::Head",
}


class TestParse:
    """parse_condition reads the subset and nothing else."""

    @pytest.mark.parametrize("text", ["", "   ", "\n"])
    def test_empty_is_no_filter(self, text: str) -> None:
        assert parse_condition(text) == Condition()

    def test_equality(self) -> None:
        assert parse_condition("component_ref = 'reachy_real/head'") == Condition(
            (Comparison(COMPONENT_REF, "=", "reachy_real/head"),)
        )

    def test_like(self) -> None:
        parsed = parse_condition("component_type LIKE 'urn:x-rois:def:component:OMG::%'")
        assert parsed.comparisons == (
            Comparison(COMPONENT_TYPE, "LIKE", "urn:x-rois:def:component:OMG::%"),
        )

    def test_and(self) -> None:
        parsed = parse_condition(
            "component_ref LIKE 'reachy_real/%' AND component_type = 'urn:t'"
        )
        assert [c.operator for c in parsed.comparisons] == ["LIKE", "="]

    def test_keywords_in_any_case(self) -> None:
        assert parse_condition("component_ref like 'r/%' and component_type = 'x'") == (
            parse_condition("component_ref LIKE 'r/%' AND component_type = 'x'")
        )

    def test_double_quoted_property(self) -> None:
        assert parse_condition('"component_ref" = \'r/head\'').comparisons[0].property == (
            COMPONENT_REF
        )

    def test_doubled_quote_in_literal(self) -> None:
        assert parse_condition("component_ref = 'it''s'").comparisons[0].value == "it's"

    def test_whitespace_is_free(self) -> None:
        assert parse_condition("  component_ref='r/head'  ") == parse_condition(
            "component_ref = 'r/head'"
        )

    @pytest.mark.parametrize(
        "text",
        [
            "component_ref = 'a' OR component_ref = 'b'",
            "NOT component_ref = 'a'",
            "(component_ref = 'a')",
            "component_ref <> 'a'",
            "component_ref = 'unterminated",
            "component_ref = reachy_real",
            "component_ref 'a'",
            "component_ref = 'a' component_type = 'b'",
            "component_ref = 'a' AND",
            "AND component_ref = 'a'",
            "component_ref LIKE 'trailing\\'",
        ],
    )
    def test_rejects_text_outside_the_subset(self, text: str) -> None:
        with pytest.raises(ConditionError):
            parse_condition(text)

    def test_rejects_unknown_property(self) -> None:
        with pytest.raises(ConditionError, match="Unsupported property 'robot'"):
            parse_condition("robot = 'reachy'")

    def test_result_filters_accept_no_property(self) -> None:
        assert parse_condition("", allowed_properties=frozenset()) == Condition()
        with pytest.raises(ConditionError, match="Supported: none"):
            parse_condition("component_ref = 'a'", allowed_properties=frozenset())

    def test_error_is_a_value_error(self) -> None:
        assert issubclass(ConditionError, ValueError)


class TestMatch:
    """Comparisons match property values the way CQL2 defines them."""

    def test_equality_is_exact(self) -> None:
        assert parse_condition("component_ref = 'reachy_real/head'").matches(HEAD)
        assert not parse_condition("component_ref = 'reachy_real/Head'").matches(HEAD)

    @pytest.mark.parametrize(
        ("pattern", "expected"),
        [
            ("reachy_real/%", True),
            ("%/head", True),
            ("reachy_real/hea_", True),
            ("reachy_sim/%", False),
            ("reachy\\_real/head", True),
            ("reachy\\%real/head", False),
            ("REACHY_REAL/%", False),
        ],
    )
    def test_like_wildcards(self, pattern: str, expected: bool) -> None:
        assert Comparison(COMPONENT_REF, "LIKE", pattern).matches(HEAD) is expected

    def test_like_escapes_regex_characters(self) -> None:
        props = {COMPONENT_REF: "a.b"}
        assert Comparison(COMPONENT_REF, "LIKE", "a.b").matches(props)
        assert not Comparison(COMPONENT_REF, "LIKE", "a.b").matches({COMPONENT_REF: "axb"})

    def test_and_needs_every_comparison(self) -> None:
        both = parse_condition("component_ref LIKE 'reachy_real/%' AND component_type = 'x'")
        assert not both.matches(HEAD)

    def test_missing_property_never_matches(self) -> None:
        assert not parse_condition("component_type = 'x'").matches({COMPONENT_REF: "a"})

    def test_empty_condition_matches_everything(self) -> None:
        assert Condition().matches({})

    def test_equal_values_drive_routing(self) -> None:
        parsed = parse_condition(
            "component_ref = 'reachy_real/head' AND component_type LIKE 'urn:%'"
        )
        assert parsed.equal_values(COMPONENT_REF) == {"reachy_real/head"}
        assert parsed.equal_values(COMPONENT_TYPE) == set()


class TestBuild:
    """The builders write text that parses back to the same condition."""

    def test_eq(self) -> None:
        assert cond.eq(COMPONENT_REF, "reachy_real/head") == "component_ref = 'reachy_real/head'"

    def test_like(self) -> None:
        assert cond.like(COMPONENT_REF, "reachy_real/%") == "component_ref LIKE 'reachy_real/%'"

    def test_quote_doubles_single_quotes(self) -> None:
        assert cond.quote("it's") == "'it''s'"

    def test_all_of_skips_empty(self) -> None:
        assert cond.all_of(cond.eq(COMPONENT_REF, "a"), "", cond.like(COMPONENT_TYPE, "u%")) == (
            "component_ref = 'a' AND component_type LIKE 'u%'"
        )

    @pytest.mark.parametrize("value", ["plain", "it's", "''", "a = 'b' AND c", "%_\\"])
    def test_round_trip(self, value: str) -> None:
        built = cond.eq(COMPONENT_REF, value)
        assert parse_condition(built).comparisons == (Comparison(COMPONENT_REF, "=", value),)

    def test_str_writes_canonical_text(self) -> None:
        parsed = parse_condition("component_ref like 'r/%'   and component_type='t'")
        assert str(parsed) == "component_ref LIKE 'r/%' AND component_type = 't'"


class TestComponentType:
    def test_urn_from_profile_identifier(self) -> None:
        identifier = RoISIdentifierType(authority="OMG", code="PersonDetection")
        assert component_type_urn(identifier) == "urn:x-rois:def:component:OMG::PersonDetection"
