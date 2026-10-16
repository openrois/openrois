"""Cross-check Pydantic models against normative XML profile files.

This test module parses the XML profile files (PersonDetection.xml, Navigation.xml,
SystemInformation.xml, Reaction.xml, SpeechSynthesis.xml, RoISCommon.xml) using lxml and
validates that the Pydantic models and the profile constants agree with the XML
definitions: field names, data types, descriptions and default values must match.

It also holds all 18 profiles to the expectations of ``_normative_expectations.py``,
asserts the XSD gaps of the validation table as they stand, and compares the Python enums
with the IDL enum bodies.
"""

import re
from dataclasses import replace

import pytest
from lxml import etree

from openrois.interfaces.common import ComponentStatus, StreamStatus
from openrois.interfaces.components import (
    NAVIGATION_PROFILE,
    PERSON_DETECTION_PROFILE,
    REACTION_PROFILE,
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    SPEECH_SYNTHESIS_PROFILE,
    SYSTEM_INFORMATION_PROFILE,
)
from openrois.interfaces.hri import ReturnCode
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.service import CompletedStatus, ErrorType
from tests import _normative_expectations as expectations
from tests._normative import NORMATIVE_DIR, requires_normative

# Every test in this module reads the normative XML profiles.
pytestmark = requires_normative

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROIS_NS = "http://www.omg.org/spec/RoIS/20240801"
GML_NS = "http://www.opengis.net/gml/3.2"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSD_NS = "http://www.w3.org/2001/XMLSchema"

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

# ---------------------------------------------------------------------------
# Tests: the profile constants
# ---------------------------------------------------------------------------

_ONTOLOGY_COMPONENT = "https://www.omg.org/spec/RoIS/Ontology/RoboticInteractionServiceComponentOntology/"
# Sensing and Actuation sit in RoboticServiceFunctionOntology; OWL.ttl puts the streaming
# types under RoboticServiceOntology/Function (row 35).
_ONTOLOGY_FUNCTION = (
    r"https://www\.omg\.org/spec/RoSO/"
    r"(?:RoboticServiceFunctionOntology/(Sensing|Actuation)|RoboticServiceOntology/(Function))"
)


def _ontology_function(code: str) -> ComponentFunction | None:
    """The RoSO class that OWL.ttl assigns to a component type, or None."""
    text = (NORMATIVE_DIR / "OWL.ttl").read_text()
    block = re.search(
        rf"<{re.escape(_ONTOLOGY_COMPONENT + code)}>(.*?)\s\.\s*$",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if block is None:
        return None
    parent = re.search(rf"rdfs:subClassOf <{_ONTOLOGY_FUNCTION}>", block.group(1))
    if parent is None:
        return None
    return ComponentFunction((parent.group(1) or parent.group(2)).lower())


def _full_profile(filename: str) -> HRIComponentProfile:
    """The full profile of a type, built from the normative files alone.

    The XML profile, with the messages of the RoIS_Common profile it includes listed
    before its own, and the RoSO function the ontology assigns to the type.
    """
    profile = _build_component_profile_from_xml(filename)
    update: dict[str, object] = {"function": _ontology_function(profile.identifier.code)}
    if ROIS_COMMON_URN in profile.sub_component_profiles:
        common = _build_component_profile_from_xml("RoISCommon.xml")
        update["command_profiles"] = [*common.command_profiles, *profile.command_profiles]
        update["query_profiles"] = [*common.query_profiles, *profile.query_profiles]
        update["event_profiles"] = [*common.event_profiles, *profile.event_profiles]
    return profile.model_copy(update=update)


@pytest.mark.parametrize(
    ("constant", "filename"),
    [
        (ROIS_COMMON_PROFILE, "RoISCommon.xml"),
        (NAVIGATION_PROFILE, "Navigation.xml"),
        (PERSON_DETECTION_PROFILE, "PersonDetection.xml"),
        (REACTION_PROFILE, "Reaction.xml"),
        (SPEECH_SYNTHESIS_PROFILE, "SpeechSynthesis.xml"),
        (SYSTEM_INFORMATION_PROFILE, "SystemInformation.xml"),
    ],
    ids=[
        "RoISCommon",
        "Navigation",
        "PersonDetection",
        "Reaction",
        "SpeechSynthesis",
        "SystemInformation",
    ],
)
def test_profile_constant_matches_xml(constant: HRIComponentProfile, filename: str) -> None:
    """Each profile constant equals the full profile built from the normative files."""
    assert constant == _full_profile(filename)


def test_rois_common_urn_matches_xml() -> None:
    """ROIS_COMMON_URN is the identifier of RoISCommon.xml and the SubComponentProfile text."""
    root = _parse_xml("RoISCommon.xml")
    assert root.find(f"{{{GML_NS}}}identifier").text == ROIS_COMMON_URN
    for filename in (
        "Navigation.xml",
        "PersonDetection.xml",
        "Reaction.xml",
        "SpeechSynthesis.xml",
    ):
        assert ROIS_COMMON_URN in _build_component_profile_from_xml(filename).sub_component_profiles


# ---------------------------------------------------------------------------
# Tests: all 18 profiles against the expectations of the validation table
# ---------------------------------------------------------------------------

_EXPECTED = {p.file: p for p in expectations.PROFILES}


def _load(filename: str) -> etree._Element:
    """Parse a profile, repairing in memory only the strict-parse defects on record."""
    data = (NORMATIVE_DIR / filename).read_bytes()
    if filename in expectations.STRICT_PARSE_DEFECTS:
        defect, repair = expectations.STRICT_PARSE_DEFECTS[filename]
        data = data.replace(defect, repair)
    return etree.fromstring(data)


def _code(element: etree._Element) -> str:
    ref = element.find(f"{{{ROIS_NS}}}data_type_ref")
    assert ref is not None, f"{element.get(f'{{{ROIS_NS}}}name')} has no data_type_ref"
    return ref.get(f"{{{ROIS_NS}}}code", "")


def _fields(element: etree._Element, tag: str) -> tuple[expectations.Field, ...]:
    return tuple(
        expectations.Field(child.get(f"{{{ROIS_NS}}}name", ""), _code(child))
        for child in element.findall(f"{{{ROIS_NS}}}{tag}")
    )


def _read_profile(filename: str) -> expectations.Profile:
    """The file as an expectation entry, without validation rows."""
    root = _load(filename)
    messages = tuple(
        expectations.Message(
            kind=m.get(f"{{{XSI_NS}}}type", "").removeprefix("rois:").removesuffix(
                "MessageProfileType"
            ),
            name=m.get(f"{{{ROIS_NS}}}name", ""),
            arguments=_fields(m, "Arguments"),
            results=_fields(m, "Results"),
        )
        for m in root.findall(f"{{{ROIS_NS}}}MessageProfile")
    )
    parameters = tuple(
        expectations.Parameter(
            name=p.get(f"{{{ROIS_NS}}}name", ""),
            code=_code(p),
            default=p.get(f"{{{ROIS_NS}}}default_value"),
        )
        for p in root.findall(f"{{{ROIS_NS}}}ParameterProfile")
    )
    return expectations.Profile(
        file=filename,
        identifier=root.findtext(f"{{{GML_NS}}}identifier", ""),
        name=root.findtext(f"{{{GML_NS}}}name", ""),
        sub_profiles=tuple(
            (s.text or "").strip() for s in root.findall(f"{{{ROIS_NS}}}SubComponentProfile")
        ),
        messages=messages,
        parameters=parameters,
    )


def _without_rows(profile: expectations.Profile) -> expectations.Profile:
    return replace(
        profile,
        messages=tuple(replace(m, rows=()) for m in profile.messages),
        parameters=tuple(replace(p, rows=()) for p in profile.parameters),
        rows=(),
    )


def _xsd_type(name: str) -> etree._Element:
    root = etree.parse(str(NORMATIVE_DIR / "XML-Profiles.xsd")).getroot()
    found = root.find(f"{{{XSD_NS}}}complexType[@name='{name}']")
    assert found is not None, f"XML-Profiles.xsd has no complexType {name}"
    return found


class TestNormativeFiles:
    """The normative directory holds the 18 profiles the expectations describe."""

    def test_profile_files_are_the_expected_eighteen(self) -> None:
        present = {p.name for p in NORMATIVE_DIR.glob("*.xml")} - {"Model.xml"}
        assert len(expectations.PROFILES) == 18
        assert present == set(expectations.PROFILE_FILES)

    @pytest.mark.parametrize(
        "filename",
        [*expectations.PROFILE_FILES, "Model.xml", "XML-Profiles.xsd"],
    )
    def test_file_parses_with_lxml(self, filename: str) -> None:
        """Every file parses strictly, except a defect on record, which must still fail.

        A corrected file turns the defect assertion red: remove its entry from
        STRICT_PARSE_DEFECTS then.
        """
        path = str(NORMATIVE_DIR / filename)
        if filename in expectations.STRICT_PARSE_DEFECTS:
            defect, _ = expectations.STRICT_PARSE_DEFECTS[filename]
            assert defect in (NORMATIVE_DIR / filename).read_bytes()
            with pytest.raises(etree.XMLSyntaxError):
                etree.parse(path)
            assert _load(filename) is not None
        else:
            assert etree.parse(path).getroot() is not None


@pytest.mark.parametrize("filename", expectations.PROFILE_FILES)
class TestProfileExpectations:
    """Each profile file matches its expectation entry."""

    def test_root_is_component_profile(self, filename: str) -> None:
        assert _load(filename).tag == f"{{{ROIS_NS}}}HRIComponentProfile"

    def test_gml_id_is_component_profile(self, filename: str) -> None:
        """Row 34: every file uses the same gml:id, so an engine profile must rename it."""
        assert _load(filename).get(f"{{{GML_NS}}}id") == "component_profile"

    def test_identifier_code_space(self, filename: str) -> None:
        identifier = _load(filename).find(f"{{{GML_NS}}}identifier")
        assert identifier is not None
        assert identifier.get("codeSpace") == "urn:ietf:rfc:2141"

    def test_profile_matches_expectation(self, filename: str) -> None:
        assert _read_profile(filename) == _without_rows(_EXPECTED[filename])

    def test_sub_profile_is_rois_common_only(self, filename: str) -> None:
        """Rows 4 and 20: RoISCommon is the only sub-profile, except where none applies."""
        sub_profiles = _read_profile(filename).sub_profiles
        if filename in ("SystemInformation.xml", "RoISCommon.xml"):
            assert sub_profiles == ()
        else:
            assert sub_profiles == (expectations.ROIS_COMMON_REF,)


def test_type_codes_are_exactly_the_twelve() -> None:
    """Rows 7 and 33: the set of type codes used across the 18 profiles."""
    used: set[str] = set()
    for filename in expectations.PROFILE_FILES:
        root = _load(filename)
        used |= {
            ref.get(f"{{{ROIS_NS}}}code", "")
            for ref in root.iter(f"{{{ROIS_NS}}}data_type_ref")
        }
    assert used == expectations.TYPE_CODES


def test_expectations_use_only_the_twelve_codes() -> None:
    codes = {
        f.code
        for p in expectations.PROFILES
        for m in p.messages
        for f in (*m.arguments, *m.results)
    } | {p.code for profile in expectations.PROFILES for p in profile.parameters}
    assert codes == expectations.TYPE_CODES


class TestXSDGapsAsTheyStand:
    """The two XSD gaps of the validation table, asserted as they stand.

    A revision of XML-Profiles.xsd that closes a gap turns its test red, so the codec
    and section 16 are revisited rather than passing silently.
    """

    def test_arguments_declared_on_command_profiles_only(self) -> None:
        """Row 9: the XSD gives Arguments to CommandMessageProfileType alone."""
        for name in ("MessageProfileType", "QueryMessageProfileType", "EventMessageProfileType"):
            elements = {e.get("name") for e in _xsd_type(name).iter(f"{{{XSD_NS}}}element")}
            assert "Arguments" not in elements, name
        command = {
            e.get("name") for e in _xsd_type("CommandMessageProfileType").iter(
                f"{{{XSD_NS}}}element"
            )
        }
        assert "Arguments" in command

    def test_arguments_present_on_query_and_event_profiles(self) -> None:
        """Row 9: the streaming profiles carry Arguments on a query and an event anyway."""
        with_arguments = {
            (filename, m.kind, m.name)
            for filename in expectations.PROFILE_FILES
            for m in _read_profile(filename).messages
            if m.arguments and m.kind != expectations.COMMAND
        }
        assert with_arguments == {
            (f, kind, name)
            for f in ("AudioStreaming.xml", "VideoStreaming.xml")
            for kind, name in (
                (expectations.QUERY, "get_stream_status"),
                (expectations.EVENT, "notify_stream_status"),
            )
        }

    def test_concurrent_commands_hold_command_list(self) -> None:
        """Row 3: ConcurrentCommandsType holds command_list of CommandMessageType."""
        elements = [
            (e.get("name"), e.get("type"))
            for e in _xsd_type("ConcurrentCommandsType").iter(f"{{{XSD_NS}}}element")
        ]
        assert elements == [("command_list", "rois:CommandMessageType")]

    def test_branch_type_unused(self) -> None:
        """Row 3: BranchType is declared, and only its own Branch element uses it."""
        root = etree.parse(str(NORMATIVE_DIR / "XML-Profiles.xsd")).getroot()
        assert _xsd_type("BranchType") is not None
        users = [e.get("name") for e in root.iter(f"{{{XSD_NS}}}element")
                 if e.get("type") == "rois:BranchType"]
        refs = [e for e in root.iter(f"{{{XSD_NS}}}element") if e.get("ref") == "rois:Branch"]
        assert users == ["Branch"]
        assert refs == []


# ---------------------------------------------------------------------------
# Tests: the Python enums against the IDL enum bodies
# ---------------------------------------------------------------------------


def _idl_enum(filename: str, name: str) -> list[str]:
    """The literals of an IDL enum, in order."""
    text = (NORMATIVE_DIR / filename).read_text()
    body = re.search(rf"\benum\s+{re.escape(name)}\s*\{{(.*?)\}}", text, re.DOTALL)
    assert body is not None, f"{filename} declares no enum {name}"
    return [literal.strip() for literal in body.group(1).split(",") if literal.strip()]


_PYTHON_ENUMS = {
    "ReturnCode": ReturnCode,
    "ComponentStatus": ComponentStatus,
    "StreamStatus": StreamStatus,
    "CompletedStatus": CompletedStatus,
    "ErrorType": ErrorType,
}


@pytest.mark.parametrize("enum_name", list(expectations.IDL_ENUMS))
def test_enum_matches_idl(enum_name: str) -> None:
    """Each enum carries the IDL literals as its values, in the IDL order."""
    filename, idl_name = expectations.IDL_ENUMS[enum_name]
    assert [m.value for m in _PYTHON_ENUMS[enum_name]] == _idl_enum(filename, idl_name)


def test_return_code_keeps_unsupported() -> None:
    """Row 2: the IDL adds UNSUPPORTED to the five codes of Table 8.1."""
    assert "UNSUPPORTED" in _idl_enum("RoIS_HRI.idl", "ReturnCode_t")
    assert ReturnCode.UNSUPPORTED.value == "UNSUPPORTED"


@pytest.mark.parametrize("code", list(expectations.ROSO_FUNCTIONS))
def test_ontology_function(code: str) -> None:
    """Row 35: the RoSO function of each type, from both ontology namespaces of OWL.ttl."""
    expected = expectations.ROSO_FUNCTIONS[code]
    assert _ontology_function(code) == (ComponentFunction(expected) if expected else None)
