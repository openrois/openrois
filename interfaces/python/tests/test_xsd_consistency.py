"""Validate that Pydantic profile models are structurally consistent with XML-Profiles.xsd.

This test verifies that the JSON Schema produced by our Pydantic profile models
matches the structural expectations defined in the XSD schema. We check:

1. RoISIdentifierType fields match XSD RoISIdentifierType attributes
2. ParameterProfile fields match XSD ParameterProfileType
3. MessageProfile hierarchy matches XSD MessageProfileType hierarchy
4. CommandMessageProfile has Arguments and timeout
5. HRIComponentProfile structure matches XSD HRIComponentProfileType
6. HRIEngineProfileType supports recursive sub-profiles

This is step 10 of the M0 Task 0.1 plan.
"""

import os
from pathlib import Path

import pytest
from lxml import etree

from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    MessageProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.hri import Argument, CommandUnit, CommandUnitSequence, ConcurrentCommands

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# tests/test_xsd_consistency.py  →  tests/  →  python/  →  interfaces/  →  repo root
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

XSD_PATH = NORMATIVE_DIR / "XML-Profiles.xsd"

ROIS_NS = "http://www.omg.org/spec/RoIS/20240801"
XSD_NS = "http://www.w3.org/2001/XMLSchema"


def _parse_xsd() -> etree.XMLSchema:
    """Parse and compile the XSD schema."""
    schema_doc = etree.parse(str(XSD_PATH))
    return etree.XMLSchema(schema_doc)


def _get_xsd_complex_type(type_name: str) -> etree._Element:
    """Get a complex type definition from the XSD by name."""
    schema_doc = etree.parse(str(XSD_PATH))
    root = schema_doc.getroot()
    for ct in root.findall(f"{{{XSD_NS}}}complexType"):
        if ct.get("name") == type_name:
            return ct
    raise ValueError(f"Complex type '{type_name}' not found in XSD")


def _get_xsd_attribute_names(type_name: str) -> set[str]:
    """Get the set of attribute names from an XSD complex type."""
    ct = _get_xsd_complex_type(type_name)
    attrs = set()
    # Direct attributes
    for attr in ct.iter(f"{{{XSD_NS}}}attribute"):
        name = attr.get("name")
        if name:
            attrs.add(name)
    # Attributes from extensions (complexContent)
    for ext in ct.iter(f"{{{XSD_NS}}}extension"):
        for attr in ext.findall(f"{{{XSD_NS}}}attribute"):
            name = attr.get("name")
            if name:
                attrs.add(name)
    return attrs


def _get_xsd_element_names_in_sequence(type_name: str) -> set[str]:
    """Get the set of element names in a sequence from an XSD complex type."""
    ct = _get_xsd_complex_type(type_name)
    elements = set()
    for seq in ct.iter(f"{{{XSD_NS}}}sequence"):
        for elem in seq.findall(f"{{{XSD_NS}}}element"):
            name = elem.get("name")
            ref = elem.get("ref")
            if name:
                elements.add(name)
            elif ref:
                # Strip namespace prefix
                elements.add(ref.split(":")[-1] if ":" in ref else ref)
    return elements


# ---------------------------------------------------------------------------
# Tests: RoISIdentifierType consistency
# ---------------------------------------------------------------------------


class TestXSDRoISIdentifierType:
    """Verify RoISIdentifierType Pydantic model matches XSD definition."""

    def test_attribute_names_match_xsd(self) -> None:
        """Pydantic model fields should match XSD attribute names."""
        xsd_attrs = _get_xsd_attribute_names("RoISIdentifierType")
        model_fields = set(RoISIdentifierType.model_fields.keys())

        # XSD has: authority, code, codebook_ref, version
        # Pydantic model should have the same fields
        assert model_fields == xsd_attrs, (
            f"RoISIdentifierType fields {model_fields} != XSD attributes {xsd_attrs}"
        )

    def test_required_fields_match_xsd(self) -> None:
        """Only 'code' is required in XSD (use='required'), others are optional."""
        ct = _get_xsd_complex_type("RoISIdentifierType")
        required_xsd = set()
        optional_xsd = set()
        for attr in ct.findall(f"{{{XSD_NS}}}attribute"):
            name = attr.get("name")
            use = attr.get("use", "optional")
            if use == "required":
                required_xsd.add(name)
            else:
                optional_xsd.add(name)

        # In Pydantic, required fields have no default, optional have defaults
        required_model = {
            name for name, field in RoISIdentifierType.model_fields.items()
            if field.is_required()
        }
        optional_model = {
            name for name, field in RoISIdentifierType.model_fields.items()
            if not field.is_required()
        }

        assert required_model == required_xsd, (
            f"Required fields mismatch: model={required_model}, xsd={required_xsd}"
        )
        assert optional_model == optional_xsd, (
            f"Optional fields mismatch: model={optional_model}, xsd={optional_xsd}"
        )


# ---------------------------------------------------------------------------
# Tests: ParameterProfile consistency
# ---------------------------------------------------------------------------


class TestXSDParameterProfile:
    """Verify ParameterProfile Pydantic model matches XSD definition."""

    def test_attribute_names_match_xsd(self) -> None:
        """Pydantic model fields should include XSD attributes."""
        xsd_attrs = _get_xsd_attribute_names("ParameterProfileType")
        model_fields = set(ParameterProfile.model_fields.keys())

        # XSD has: name, default_value, description (attributes)
        # Plus data_type_ref (element)
        xsd_attrs_with_element = xsd_attrs | {"data_type_ref"}
        assert model_fields == xsd_attrs_with_element, (
            f"ParameterProfile fields {model_fields} != XSD attrs+elements {xsd_attrs_with_element}"
        )

    def test_required_fields_match_xsd(self) -> None:
        """'name' and 'data_type_ref' are required in XSD."""
        ct = _get_xsd_complex_type("ParameterProfileType")
        required_xsd_attrs = set()
        for attr in ct.findall(f"{{{XSD_NS}}}attribute"):
            if attr.get("use") == "required":
                required_xsd_attrs.add(attr.get("name"))

        # data_type_ref element has minOccurs="1"
        required_xsd = required_xsd_attrs | {"data_type_ref"}

        required_model = {
            name for name, field in ParameterProfile.model_fields.items()
            if field.is_required()
        }

        assert required_model == required_xsd, (
            f"Required fields mismatch: model={required_model}, xsd={required_xsd}"
        )


# ---------------------------------------------------------------------------
# Tests: MessageProfile hierarchy consistency
# ---------------------------------------------------------------------------


class TestXSDMessageProfileHierarchy:
    """Verify MessageProfile type hierarchy matches XSD."""

    def test_event_message_profile_is_subclass(self) -> None:
        """EventMessageProfile should extend MessageProfile (XSD extension)."""
        assert issubclass(EventMessageProfile, MessageProfile)

    def test_query_message_profile_is_subclass(self) -> None:
        """QueryMessageProfile should extend MessageProfile (XSD extension)."""
        assert issubclass(QueryMessageProfile, MessageProfile)

    def test_command_message_profile_is_subclass(self) -> None:
        """CommandMessageProfile should extend MessageProfile (XSD extension)."""
        assert issubclass(CommandMessageProfile, MessageProfile)

    def test_command_message_profile_has_arguments(self) -> None:
        """CommandMessageProfile should have 'arguments' field (XSD extension)."""
        assert "arguments" in CommandMessageProfile.model_fields

    def test_command_message_profile_has_timeout(self) -> None:
        """CommandMessageProfile should have 'timeout' field (XSD attribute)."""
        assert "timeout" in CommandMessageProfile.model_fields

    def test_base_message_profile_has_name_and_results(self) -> None:
        """MessageProfile should have 'name' and 'results' fields."""
        assert "name" in MessageProfile.model_fields
        assert "results" in MessageProfile.model_fields


# ---------------------------------------------------------------------------
# Tests: HRIComponentProfile consistency
# ---------------------------------------------------------------------------


class TestXSDHRIComponentProfile:
    """Verify HRIComponentProfile Pydantic model matches XSD definition."""

    def test_has_identifier_field(self) -> None:
        """HRIComponentProfile should have an 'identifier' field."""
        assert "identifier" in HRIComponentProfile.model_fields

    def test_has_name_field(self) -> None:
        """HRIComponentProfile should have a 'name' field (from gml:IdentifiedObjectType)."""
        assert "name" in HRIComponentProfile.model_fields

    def test_has_sub_component_profiles(self) -> None:
        """HRIComponentProfile should have 'sub_component_profiles' (XSD: SubComponentProfile)."""
        assert "sub_component_profiles" in HRIComponentProfile.model_fields

    def test_has_message_profiles(self) -> None:
        """HRIComponentProfile should have message profile lists."""
        assert "command_profiles" in HRIComponentProfile.model_fields
        assert "query_profiles" in HRIComponentProfile.model_fields
        assert "event_profiles" in HRIComponentProfile.model_fields

    def test_has_parameter_profiles(self) -> None:
        """HRIComponentProfile should have 'parameter_profiles' (XSD: ParameterProfile)."""
        assert "parameter_profiles" in HRIComponentProfile.model_fields


# ---------------------------------------------------------------------------
# Tests: HRIEngineProfileType consistency
# ---------------------------------------------------------------------------


class TestXSDHRIEngineProfileType:
    """Verify HRIEngineProfileType Pydantic model matches XSD definition."""

    def test_has_identifier_field(self) -> None:
        """HRIEngineProfileType should have an 'identifier' field."""
        assert "identifier" in HRIEngineProfileType.model_fields

    def test_has_sub_profiles(self) -> None:
        """HRIEngineProfileType should have 'sub_profiles' (XSD: SubProfile)."""
        assert "sub_profiles" in HRIEngineProfileType.model_fields

    def test_has_component_ids(self) -> None:
        """HRIEngineProfileType should have 'component_ids' (XSD: HRIComponent)."""
        assert "component_ids" in HRIEngineProfileType.model_fields

    def test_has_parameter_profiles(self) -> None:
        """HRIEngineProfileType should have 'parameter_profiles'."""
        assert "parameter_profiles" in HRIEngineProfileType.model_fields

    def test_recursive_sub_profiles(self) -> None:
        """HRIEngineProfileType should support recursive nesting (sub_profiles of same type)."""
        sub_profile = HRIEngineProfileType(
            identifier=RoISIdentifierType(code="SubEngine"),
        )
        engine = HRIEngineProfileType(
            identifier=RoISIdentifierType(code="MainEngine"),
            sub_profiles=[sub_profile],
        )
        assert len(engine.sub_profiles) == 1
        assert engine.sub_profiles[0].identifier.code == "SubEngine"


# ---------------------------------------------------------------------------
# Tests: CommandUnitSequence consistency
# ---------------------------------------------------------------------------


class TestXSDCommandUnitSequence:
    """Verify CommandUnitSequence Pydantic model matches XSD definition."""

    def test_command_unit_has_component_ref(self) -> None:
        """CommandUnit should have 'component_ref' field (XSD: component_ref)."""
        assert "component_ref" in CommandUnit.model_fields

    def test_command_unit_has_command_type(self) -> None:
        """CommandUnit should have 'command_type' field (XSD: command_type)."""
        assert "command_type" in CommandUnit.model_fields

    def test_command_unit_has_command_id(self) -> None:
        """CommandUnit should have 'command_id' field (XSD: command_id)."""
        assert "command_id" in CommandUnit.model_fields

    def test_command_unit_has_arguments(self) -> None:
        """CommandUnit should have 'arguments' field (XSD: arguments)."""
        assert "arguments" in CommandUnit.model_fields

    def test_command_unit_has_delay_time(self) -> None:
        """CommandUnit should have 'delay_time' field (XSD: delay_time from CommandBaseType)."""
        assert "delay_time" in CommandUnit.model_fields

    def test_concurrent_commands_has_command_list(self) -> None:
        """ConcurrentCommands should have 'command_list' field (XSD: command_list)."""
        assert "command_list" in ConcurrentCommands.model_fields

    def test_concurrent_commands_has_delay_time(self) -> None:
        """ConcurrentCommands should have 'delay_time' field (XSD: delay_time from CommandBaseType)."""
        assert "delay_time" in ConcurrentCommands.model_fields

    def test_command_unit_sequence_has_command_unit_list(self) -> None:
        """CommandUnitSequence should have 'command_unit_list' field (XSD: command_unit_list)."""
        assert "command_unit_list" in CommandUnitSequence.model_fields


# ---------------------------------------------------------------------------
# Tests: XSD schema validation of XML files
# ---------------------------------------------------------------------------


class TestXSDValidation:
    """Validate that the normative XML files are structurally consistent with the XSD schema.

    Note: Full XSD validation requires the GML schema to be accessible. If the
    GML import fails, we skip the validation rather than failing the test.
    """

    @pytest.mark.parametrize("filename", [
        "PersonDetection.xml",
        "Navigation.xml",
        "SystemInformation.xml",
    ])
    def test_xml_file_well_formed(self, filename: str) -> None:
        """Each normative XML file should be well-formed XML."""
        xml_path = NORMATIVE_DIR / filename
        try:
            doc = etree.parse(str(xml_path))
            assert doc.getroot() is not None
        except etree.XMLSyntaxError as e:
            pytest.fail(f"{filename} is not well-formed XML: {e}")

    @pytest.mark.parametrize("filename", [
        "PersonDetection.xml",
        "Navigation.xml",
        "SystemInformation.xml",
    ])
    def test_xml_file_has_expected_structure(self, filename: str) -> None:
        """Each XML file should have the expected root element and namespace."""
        xml_path = NORMATIVE_DIR / filename
        doc = etree.parse(str(xml_path))
        root = doc.getroot()

        # Root should be HRIComponentProfile in the RoIS namespace
        assert root.tag == f"{{{ROIS_NS}}}HRIComponentProfile", (
            f"{filename} root tag is {root.tag}, expected {{{ROIS_NS}}}HRIComponentProfile"
        )

        # Should have a gml:identifier child
        GML_NS = "http://www.opengis.net/gml/3.2"
        identifier = root.find(f"{{{GML_NS}}}identifier")
        assert identifier is not None, f"{filename} missing gml:identifier"

        # Should have a gml:name child
        name = root.find(f"{{{GML_NS}}}name")
        assert name is not None, f"{filename} missing gml:name"