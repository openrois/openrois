"""Cross-check Pydantic models against normative XML profile files.

This test module parses the XML profile files (PersonDetection.xml, Navigation.xml,
SystemInformation.xml) using lxml and validates that the Pydantic models agree with
the XML definitions — field names, data types, and default values must match.

This is step 9 of the M0 Task 0.1 plan.
"""

import os
from pathlib import Path

import pytest
from lxml import etree

from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# tests/test_xml_crosscheck.py  →  tests/  →  python/  →  interfaces/  →  repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
# The OMG machine-readable files are not redistributed in this repository. Point
# OPENROIS_NORMATIVE_DIR at a directory containing them to run these tests.
NORMATIVE_DIR = Path(
    os.environ.get("OPENROIS_NORMATIVE_DIR", REPO_ROOT / "normative" / "machine-readable")
)

pytestmark = pytest.mark.skipif(
    not NORMATIVE_DIR.is_dir(),
    reason="normative RoIS files not available (set OPENROIS_NORMATIVE_DIR)",
)

ROIS_NS = "http://www.omg.org/spec/RoIS/20240801"
GML_NS = "http://www.opengis.net/gml/3.2"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

NAMESPACES = {
    "rois": ROIS_NS,
    "gml": GML_NS,
    "xsi": XSI_NS,
}


def _parse_xml(filename: str) -> etree._Element:
    """Parse an XML file from the normative directory."""
    path = NORMATIVE_DIR / filename
    tree = etree.parse(str(path))
    return tree.getroot()


def _extract_identifier(root: etree._Element) -> dict:
    """Extract the gml:identifier element into a RoISIdentifierType dict."""
    ident_elem = root.find(f"{{{GML_NS}}}identifier")
    assert ident_elem is not None, "No gml:identifier found in XML"

    # The identifier text is the URN, e.g., "urn:x-rois:def:component:OMG::PersonDetection"
    urn = ident_elem.text or ""
    code_space = ident_elem.get(f"{{{GML_NS}}}codeSpace", "")

    # Parse the URN to extract authority and code
    # Format: urn:x-rois:def:component:AUTHORITY::CODE
    parts = urn.split("::")
    if len(parts) == 2:
        authority = parts[0].split(":")[-1]
        code = parts[1]
    else:
        authority = ""
        code = urn

    return {
        "authority": authority,
        "code": code,
        "codebook_ref": "",
        "version": "",
    }


def _extract_name(root: etree._Element) -> str:
    """Extract the gml:name element text."""
    name_elem = root.find(f"{{{GML_NS}}}name")
    assert name_elem is not None, "No gml:name found in XML"
    return name_elem.text or ""


def _extract_parameter_profiles(root: etree._Element) -> list[dict]:
    """Extract ParameterProfile elements from the XML."""
    profiles = []
    for pp_elem in root.findall(f"{{{ROIS_NS}}}ParameterProfile"):
        name = pp_elem.get(f"{{{ROIS_NS}}}name", "")
        default_value = pp_elem.get(f"{{{ROIS_NS}}}default_value", "")
        description = pp_elem.get(f"{{{ROIS_NS}}}description", "")

        # Extract data_type_ref
        dt_ref_elem = pp_elem.find(f"{{{ROIS_NS}}}data_type_ref")
        dt_code = dt_ref_elem.get(f"{{{ROIS_NS}}}code", "") if dt_ref_elem is not None else ""

        profiles.append({
            "name": name,
            "data_type_ref": {"authority": "", "code": dt_code, "codebook_ref": "", "version": ""},
            "default_value": default_value,
            "description": description,
        })
    return profiles


def _extract_message_profiles(root: etree._Element) -> tuple[list, list, list]:
    """Extract message profiles from the XML, categorized by type."""
    command_profiles = []
    query_profiles = []
    event_profiles = []

    for mp_elem in root.findall(f"{{{ROIS_NS}}}MessageProfile"):
        name = mp_elem.get(f"{{{ROIS_NS}}}name", "")
        xsi_type = mp_elem.get(f"{{{XSI_NS}}}type", "")

        # Extract Results (ParameterProfile elements)
        results = []
        for res_elem in mp_elem.findall(f"{{{ROIS_NS}}}Results"):
            res_name = res_elem.get(f"{{{ROIS_NS}}}name", "")
            res_desc = res_elem.get(f"{{{ROIS_NS}}}description", "")
            dt_ref_elem = res_elem.find(f"{{{ROIS_NS}}}data_type_ref")
            dt_code = dt_ref_elem.get(f"{{{ROIS_NS}}}code", "") if dt_ref_elem is not None else ""

            results.append({
                "name": res_name,
                "data_type_ref": {"authority": "", "code": dt_code, "codebook_ref": "", "version": ""},
                "default_value": "",
                "description": res_desc,
            })

        # Extract Arguments (for CommandMessageProfile)
        arguments = []
        for arg_elem in mp_elem.findall(f"{{{ROIS_NS}}}Arguments"):
            arg_name = arg_elem.get(f"{{{ROIS_NS}}}name", "")
            arg_desc = arg_elem.get(f"{{{ROIS_NS}}}description", "")
            dt_ref_elem = arg_elem.find(f"{{{ROIS_NS}}}data_type_ref")
            dt_code = dt_ref_elem.get(f"{{{ROIS_NS}}}code", "") if dt_ref_elem is not None else ""

            arguments.append({
                "name": arg_name,
                "data_type_ref": {"authority": "", "code": dt_code, "codebook_ref": "", "version": ""},
                "default_value": "",
                "description": arg_desc,
            })

        # Extract timeout (for CommandMessageProfile)
        timeout = mp_elem.get(f"{{{ROIS_NS}}}timeout")
        timeout_int = int(timeout) if timeout else None

        profile_dict = {
            "name": name,
            "results": results,
        }

        if "CommandMessageProfileType" in xsi_type:
            profile_dict["arguments"] = arguments
            if timeout_int is not None:
                profile_dict["timeout"] = timeout_int
            command_profiles.append(profile_dict)
        elif "QueryMessageProfileType" in xsi_type:
            query_profiles.append(profile_dict)
        elif "EventMessageProfileType" in xsi_type:
            event_profiles.append(profile_dict)
        else:
            # Default to base MessageProfile
            event_profiles.append(profile_dict)

    return command_profiles, query_profiles, event_profiles


def _build_component_profile_from_xml(filename: str) -> HRIComponentProfile:
    """Parse an XML profile file and build an HRIComponentProfile model."""
    root = _parse_xml(filename)

    identifier = _extract_identifier(root)
    name = _extract_name(root)

    # Extract sub-component profiles
    sub_profiles = []
    for scp_elem in root.findall(f"{{{ROIS_NS}}}SubComponentProfile"):
        if scp_elem.text:
            sub_profiles.append(scp_elem.text.strip())

    command_profiles, query_profiles, event_profiles = _extract_message_profiles(root)
    parameter_profiles = _extract_parameter_profiles(root)

    return HRIComponentProfile(
        identifier=RoISIdentifierType(**identifier),
        name=name,
        sub_component_profiles=sub_profiles,
        command_profiles=[CommandMessageProfile(**cp) for cp in command_profiles],
        query_profiles=[QueryMessageProfile(**qp) for qp in query_profiles],
        event_profiles=[EventMessageProfile(**ep) for ep in event_profiles],
        parameter_profiles=[ParameterProfile(**pp) for pp in parameter_profiles],
    )


# ---------------------------------------------------------------------------
# Tests: PersonDetection.xml
# ---------------------------------------------------------------------------


class TestPersonDetectionXMLCrossCheck:
    """Cross-check PersonDetection Pydantic models against PersonDetection.xml."""

    def test_identifier_matches_xml(self) -> None:
        """The component URN and identifier should match the XML profile."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert profile.identifier.authority == "OMG"
        assert profile.identifier.code == "PersonDetection"

    def test_name_matches_xml(self) -> None:
        """The component name should match the XML profile."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert profile.name == "person_detecter"

    def test_sub_component_profiles(self) -> None:
        """PersonDetection should reference RoISCommon as sub-component."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert len(profile.sub_component_profiles) >= 1
        assert any("RoISCommon" in scp for scp in profile.sub_component_profiles)

    def test_event_profiles_match_xml(self) -> None:
        """The person_detected event profile should match the XML definition."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert len(profile.event_profiles) == 1

        event = profile.event_profiles[0]
        assert event.name == "person_detected"

        # The XML defines two results: number (int) and timestamp (DateTime)
        assert len(event.results) == 2
        result_names = {r.name for r in event.results}
        assert "number" in result_names
        assert "timestamp" in result_names

        # Check data types
        for r in event.results:
            if r.name == "number":
                assert r.data_type_ref.code == "int"
            elif r.name == "timestamp":
                assert r.data_type_ref.code == "DateTime"

    def test_no_command_profiles(self) -> None:
        """PersonDetection has no component-specific commands in the XML."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert len(profile.command_profiles) == 0

    def test_no_query_profiles(self) -> None:
        """PersonDetection has no component-specific queries in the XML."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert len(profile.query_profiles) == 0

    def test_no_parameter_profiles(self) -> None:
        """PersonDetection has no component-specific parameters in the XML."""
        profile = _build_component_profile_from_xml("PersonDetection.xml")
        assert len(profile.parameter_profiles) == 0

    def test_typed_event_fields_match_xml(self) -> None:
        """The PersonDetectedEvent typed model fields should match the XML event results."""
        from openrois.interfaces.components.person_detection import PersonDetectedEvent

        profile = _build_component_profile_from_xml("PersonDetection.xml")
        event_profile = profile.event_profiles[0]

        # The typed model should have fields corresponding to the XML results
        event_fields = PersonDetectedEvent.model_fields
        xml_result_names = {r.name for r in event_profile.results}
        for field_name in event_fields:
            assert field_name in xml_result_names, (
                f"PersonDetectedEvent has field '{field_name}' not in XML results"
            )


# ---------------------------------------------------------------------------
# Tests: Navigation.xml
# ---------------------------------------------------------------------------


class TestNavigationXMLCrossCheck:
    """Cross-check Navigation Pydantic models against Navigation.xml."""

    def test_identifier_matches_xml(self) -> None:
        """The component URN and identifier should match the XML profile."""
        profile = _build_component_profile_from_xml("Navigation.xml")
        assert profile.identifier.authority == "OMG"
        assert profile.identifier.code == "Navigation"

    def test_name_matches_xml(self) -> None:
        """The component name should match the XML profile."""
        profile = _build_component_profile_from_xml("Navigation.xml")
        assert profile.name == "navigation"

    def test_event_profiles_match_xml(self) -> None:
        """The reached_target event profile should match the XML definition."""
        profile = _build_component_profile_from_xml("Navigation.xml")
        assert len(profile.event_profiles) == 1

        event = profile.event_profiles[0]
        assert event.name == "reached_target"

        # The XML defines two results: target (string) and is_final_target (bool)
        assert len(event.results) == 2
        result_names = {r.name for r in event.results}
        assert "target" in result_names
        assert "is_final_target" in result_names

        for r in event.results:
            if r.name == "target":
                assert r.data_type_ref.code == "string"
            elif r.name == "is_final_target":
                assert r.data_type_ref.code == "bool"

    def test_parameter_profiles_match_xml(self) -> None:
        """The parameter profiles should match the XML definition."""
        profile = _build_component_profile_from_xml("Navigation.xml")
        assert len(profile.parameter_profiles) == 3

        param_names = {p.name for p in profile.parameter_profiles}
        assert "target_positions" in param_names
        assert "time_limit" in param_names
        assert "routing_policy" in param_names

        # Check data types and defaults
        for p in profile.parameter_profiles:
            if p.name == "target_positions":
                assert p.data_type_ref.code == "string[]"
            elif p.name == "time_limit":
                assert p.data_type_ref.code == "int"
                assert p.default_value == "0"
            elif p.name == "routing_policy":
                assert p.data_type_ref.code == "string"
                assert p.default_value == "time"

    def test_typed_event_fields_match_xml(self) -> None:
        """The NavigationReachedTargetEvent typed model fields should match the XML event results."""
        from openrois.interfaces.components.navigation import NavigationReachedTargetEvent

        profile = _build_component_profile_from_xml("Navigation.xml")
        event_profile = profile.event_profiles[0]

        event_fields = NavigationReachedTargetEvent.model_fields
        xml_result_names = {r.name for r in event_profile.results}
        for field_name in event_fields:
            assert field_name in xml_result_names, (
                f"NavigationReachedTargetEvent has field '{field_name}' not in XML results"
            )


# ---------------------------------------------------------------------------
# Tests: SystemInformation.xml
# ---------------------------------------------------------------------------


class TestSystemInformationXMLCrossCheck:
    """Cross-check SystemInformation profile against SystemInformation.xml."""

    def test_identifier_matches_xml(self) -> None:
        """The component URN and identifier should match the XML profile."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        assert profile.identifier.authority == "OMG"
        assert profile.identifier.code == "SystemInformation"

    def test_name_matches_xml(self) -> None:
        """The component name should match the XML profile."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        assert profile.name == "system_info"

    def test_query_profiles_match_xml(self) -> None:
        """SystemInformation should have two query profiles: robot_position and engine_status."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        assert len(profile.query_profiles) == 2

        query_names = {q.name for q in profile.query_profiles}
        assert "robot_position" in query_names
        assert "engine_status" in query_names

    def test_robot_position_query_results(self) -> None:
        """The robot_position query should have the correct result fields."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        robot_pos = next(q for q in profile.query_profiles if q.name == "robot_position")

        result_names = {r.name for r in robot_pos.results}
        assert "position_data" in result_names
        assert "robot_ref" in result_names
        assert "timestamp" in result_names

        for r in robot_pos.results:
            if r.name == "position_data":
                assert r.data_type_ref.code == "String[]"
            elif r.name == "robot_ref":
                assert r.data_type_ref.code == "RoISIdentifier[]"
            elif r.name == "timestamp":
                assert r.data_type_ref.code == "DateTime"

    def test_engine_status_query_results(self) -> None:
        """The engine_status query should have the correct result fields."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        engine_status = next(q for q in profile.query_profiles if q.name == "engine_status")

        result_names = {r.name for r in engine_status.results}
        assert "operable_time" in result_names
        assert "status" in result_names

        for r in engine_status.results:
            if r.name == "operable_time":
                assert r.data_type_ref.code == "DateTime"
            elif r.name == "status":
                assert r.data_type_ref.code == "Component_Status"

    def test_no_event_profiles(self) -> None:
        """SystemInformation has no event profiles in the XML."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        assert len(profile.event_profiles) == 0

    def test_no_command_profiles(self) -> None:
        """SystemInformation has no command profiles in the XML."""
        profile = _build_component_profile_from_xml("SystemInformation.xml")
        assert len(profile.command_profiles) == 0