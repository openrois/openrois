"""Tests for openrois.interfaces.xmlcodec, the RoIS XML reader and writer (stream I, steps 3, 4).

The samples in this module are written for the tests. The normative profiles are read
from OPENROIS_NORMATIVE_DIR and never copied into the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from openrois.interfaces.hri import (
    Argument,
    Branch,
    CommandUnit,
    CommandUnitSequence,
    ConcurrentCommands,
)
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    EventMessageProfile,
    HRIComponentProfile,
    HRIEngineProfileType,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)
from openrois.interfaces.xmlcodec import (
    GML_NS,
    ROIS_NS,
    ProfileFormatError,
    ProfileRegistry,
    UnresolvedProfileError,
    component_urn,
    parse_urn,
    read_command_message,
    read_command_unit_sequence,
    read_component_profile,
    read_engine_profile,
    write_command_unit_sequence,
    write_component_profile,
    write_engine_bundle,
    write_engine_profile,
)
from tests._normative import NORMATIVE_DIR, requires_normative

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
GML_STUB = Path(__file__).parent / "gml_stub.xsd"

PROFILE_FILES = sorted(
    p.name for p in NORMATIVE_DIR.glob("*.xml") if p.name != "Model.xml"
) if NORMATIVE_DIR.is_dir() else []

# Validation row 9: the XSD has no Arguments on query and event profiles, and these two
# profiles have them, so neither the files nor their written form validate.
XSD_GAP_FILES = {"AudioStreaming.xml", "VideoStreaming.xml"}

ROIS_COMMON = "urn:x-rois:def:Component:OMG::RoISCommon"
GRIPPER = "urn:x-rois:def:component:ACME::Gripper"
SUB1 = "urn:x-rois:def:HRIEngine:ACME::Sub1"

HEADER = (
    f'xmlns:rois="{ROIS_NS}" xmlns:gml="{GML_NS}" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
)


def _code(code: str) -> RoISIdentifierType:
    return RoISIdentifierType(code=code)


def _param(name: str, code: str, description: str = "") -> ParameterProfile:
    return ParameterProfile(name=name, data_type_ref=_code(code), description=description)


def _registry() -> ProfileRegistry:
    registry = ProfileRegistry()
    registry.load(NORMATIVE_DIR / "RoISCommon.xml")
    return registry


def _schema() -> etree.XMLSchema:
    class _GmlStub(etree.Resolver):
        def resolve(self, url, pubid, context):  # type: ignore[no-untyped-def]
            if "opengis.net" in url:
                return self.resolve_filename(str(GML_STUB), context)
            return None

    parser = etree.XMLParser(no_network=True)
    parser.resolvers.add(_GmlStub())
    return etree.XMLSchema(etree.parse(str(NORMATIVE_DIR / "XML-Profiles.xsd"), parser))


def _children(xml: bytes, local: str) -> list[etree._Element]:
    return [e for e in etree.fromstring(xml) if etree.QName(e).localname == local]


# ---------------------------------------------------------------------------
# URNs
# ---------------------------------------------------------------------------


class TestUrn:
    def test_parse_component_urn(self) -> None:
        assert parse_urn("urn:x-rois:def:component:OMG::Navigation") == RoISIdentifierType(
            authority="OMG", code="Navigation"
        )

    def test_parse_keeps_an_unstructured_urn_as_the_code(self) -> None:
        assert parse_urn("urn:x-rois:def:HRIComponent:ATR:PersonDetection") == _code(
            "urn:x-rois:def:HRIComponent:ATR:PersonDetection"
        )

    def test_component_urn(self) -> None:
        identifier = RoISIdentifierType(authority="OMG", code="Navigation")
        assert component_urn(identifier) == "urn:x-rois:def:component:OMG::Navigation"

    def test_component_urn_of_a_bare_code(self) -> None:
        assert component_urn(_code("urn:example:thing")) == "urn:example:thing"


# ---------------------------------------------------------------------------
# Reader: component profiles
# ---------------------------------------------------------------------------

SAMPLE_PROFILE = f"""<?xml version="1.0" encoding="UTF-8"?>
<rois:HRIComponentProfile gml:id="component_profile" {HEADER}>
  <gml:identifier codeSpace="urn:ietf:rfc:2141">{GRIPPER}</gml:identifier>
  <gml:name>gripper</gml:name>
  <rois:SubComponentProfile>{ROIS_COMMON}</rois:SubComponentProfile>
  <rois:MessageProfile rois:name="grip" rois:timeout="500"
      xsi:type="rois:CommandMessageProfileType">
    <rois:Results rois:name="held"><rois:data_type_ref rois:code="bool"/></rois:Results>
    <rois:Arguments rois:name="force" rois:description="grip force in N">
      <rois:data_type_ref rois:code="int"/>
    </rois:Arguments>
  </rois:MessageProfile>
  <rois:MessageProfile rois:name="hold_state" xsi:type="rois:QueryMessageProfileType">
    <rois:Arguments rois:name="finger"><rois:data_type_ref rois:code="int"/></rois:Arguments>
    <rois:Results rois:name="closed"><rois:data_type_ref rois:code="bool"/></rois:Results>
  </rois:MessageProfile>
  <rois:EventMessageProfile rois:name="dropped"/>
  <rois:ParameterProfile rois:name="speed" rois:default_value="">
    <rois:data_type_ref rois:code="int"/>
  </rois:ParameterProfile>
  <rois:ParameterProfile rois:name="mode" rois:default_value="soft">
    <rois:data_type_ref rois:code="string"/>
  </rois:ParameterProfile>
</rois:HRIComponentProfile>
"""

SAMPLE_RAW = HRIComponentProfile(
    identifier=RoISIdentifierType(authority="ACME", code="Gripper"),
    name="gripper",
    sub_component_profiles=[ROIS_COMMON],
    command_profiles=[
        CommandMessageProfile(
            name="grip",
            timeout=500,
            results=[_param("held", "bool")],
            arguments=[_param("force", "int", "grip force in N")],
        ),
    ],
    query_profiles=[
        QueryMessageProfile(
            name="hold_state",
            arguments=[_param("finger", "int")],
            results=[_param("closed", "bool")],
        ),
    ],
    event_profiles=[EventMessageProfile(name="dropped")],
    parameter_profiles=[
        _param("speed", "int"),
        ParameterProfile(name="mode", data_type_ref=_code("string"), default_value="soft"),
    ],
)


class TestReadComponentProfile:
    def test_reads_every_part(self) -> None:
        assert read_component_profile(SAMPLE_PROFILE) == SAMPLE_RAW

    def test_reads_bytes(self) -> None:
        assert read_component_profile(SAMPLE_PROFILE.encode()) == SAMPLE_RAW

    def test_reads_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "Gripper.xml"
        path.write_text(SAMPLE_PROFILE)
        assert read_component_profile(path) == SAMPLE_RAW

    def test_message_profile_needs_a_known_type(self) -> None:
        bad = SAMPLE_PROFILE.replace("rois:QueryMessageProfileType", "rois:OtherType")
        with pytest.raises(ProfileFormatError):
            read_component_profile(bad)

    def test_rejects_another_root(self) -> None:
        with pytest.raises(ProfileFormatError):
            read_component_profile(f"<rois:CommandUnitSequence {HEADER}/>")

    def test_rejects_malformed_xml(self) -> None:
        with pytest.raises(ProfileFormatError):
            read_component_profile("<rois:HRIComponentProfile")

    def test_does_not_load_external_entities(self) -> None:
        doc = SAMPLE_PROFILE.replace(
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<?xml version="1.0"?>\n<!DOCTYPE x [<!ENTITY ext SYSTEM "file:///etc/hostname">]>',
        ).replace("<gml:name>gripper</gml:name>", "<gml:name>&ext;</gml:name>")
        profile = read_component_profile(doc)
        assert profile.name == ""

    def test_reads_the_20250801_namespace(self) -> None:
        """Question 6: the published set is hosted under /spec/RoIS/20250801/."""
        doc = SAMPLE_PROFILE.replace(
            f'xmlns:rois="{ROIS_NS}"', 'xmlns:rois="http://www.omg.org/spec/RoIS/20250801"'
        )
        profile = read_component_profile(doc)
        assert profile == SAMPLE_RAW
        assert etree.fromstring(write_component_profile(profile)).nsmap["rois"] == ROIS_NS

    def test_tolerates_a_namespace_with_a_trailing_space(self) -> None:
        """Row 36: the reader trims the URI, the writer emits the correct one."""
        doc = SAMPLE_PROFILE.replace(f'xmlns:rois="{ROIS_NS}"', f'xmlns:rois="{ROIS_NS} "')
        profile = read_component_profile(doc)
        assert profile == SAMPLE_RAW
        assert etree.fromstring(write_component_profile(profile)).nsmap["rois"] == ROIS_NS


class TestRegistry:
    def test_resolves_sub_component_messages_first(self) -> None:
        registry = ProfileRegistry()
        common = HRIComponentProfile(
            identifier=RoISIdentifierType(authority="OMG", code="RoISCommon"),
            name="rois_common",
            command_profiles=[CommandMessageProfile(name="start")],
            query_profiles=[QueryMessageProfile(name="component_status")],
        )
        registry.add(common)
        profile = read_component_profile(SAMPLE_PROFILE, registry=registry)
        assert [c.name for c in profile.command_profiles] == ["start", "grip"]
        assert [q.name for q in profile.query_profiles] == ["component_status", "hold_state"]
        assert profile.sub_component_profiles == [ROIS_COMMON]

    def test_unknown_reference_raises(self) -> None:
        with pytest.raises(UnresolvedProfileError):
            read_component_profile(SAMPLE_PROFILE, registry=ProfileRegistry())

    def test_lookup_ignores_the_case_of_the_kind(self) -> None:
        registry = ProfileRegistry()
        registry.add(SAMPLE_RAW)
        assert registry.get("urn:x-rois:def:Component:ACME::Gripper") == SAMPLE_RAW
        assert "urn:x-rois:def:component:ACME::Gripper" in registry


@requires_normative
class TestReadNormativeProfiles:
    def test_reads_all_eighteen(self) -> None:
        registry = _registry()
        assert len(PROFILE_FILES) == 18
        for filename in PROFILE_FILES:
            read_component_profile(NORMATIVE_DIR / filename, registry=registry)

    def test_navigation(self) -> None:
        profile = read_component_profile(NORMATIVE_DIR / "Navigation.xml")
        assert profile.identifier == RoISIdentifierType(authority="OMG", code="Navigation")
        assert profile.name == "navigation"
        assert profile.sub_component_profiles == [ROIS_COMMON]
        assert [e.name for e in profile.event_profiles] == ["reached_target"]
        params = {p.name: p.default_value for p in profile.parameter_profiles}
        assert params == {"target_positions": None, "time_limit": "0", "routing_policy": "time"}

    def test_navigation_with_rois_common(self) -> None:
        profile = read_component_profile(NORMATIVE_DIR / "Navigation.xml", registry=_registry())
        assert [c.name for c in profile.command_profiles] == ["start", "stop", "suspend", "resume"]
        assert [q.name for q in profile.query_profiles] == ["component_status"]

    def test_streaming_arguments_on_query_and_event(self) -> None:
        """Validation row 9: stream_id is an argument of the query and the event."""
        profile = read_component_profile(NORMATIVE_DIR / "AudioStreaming.xml")
        query = next(q for q in profile.query_profiles if q.name == "get_stream_status")
        event = next(e for e in profile.event_profiles if e.name == "notify_stream_status")
        assert [a.name for a in query.arguments] == ["stream_id"]
        assert [a.name for a in event.arguments] == ["stream_id"]
        assert [r.name for r in event.results] == ["timestamp", "status"]

    def test_empty_default_is_none(self) -> None:
        """Validation row 22: default_value="" on an int means no default."""
        profile = read_component_profile(NORMATIVE_DIR / "PersonLocalization.xml")
        assert profile.parameter_profiles
        assert all(p.default_value is None for p in profile.parameter_profiles)

    def test_face_localization_namespace(self) -> None:
        """FaceLocalization.xml declares the RoIS namespace with a trailing space."""
        profile = read_component_profile(NORMATIVE_DIR / "FaceLocalization.xml")
        assert profile.identifier.code == "FaceLocalization"
        assert profile.event_profiles


# ---------------------------------------------------------------------------
# Writer: component profiles
# ---------------------------------------------------------------------------


class TestWriteComponentProfile:
    def test_round_trip(self) -> None:
        assert read_component_profile(write_component_profile(SAMPLE_RAW)) == SAMPLE_RAW

    def test_identity_and_gml_id(self) -> None:
        root = etree.fromstring(write_component_profile(SAMPLE_RAW))
        assert root.get(f"{{{GML_NS}}}id") == "component_profile"
        identifier = root.find(f"{{{GML_NS}}}identifier")
        assert identifier is not None
        assert identifier.text == "urn:x-rois:def:component:ACME::Gripper"
        assert identifier.get("codeSpace") == "urn:ietf:rfc:2141"

    def test_command_results_come_before_arguments(self) -> None:
        """XSD order: CommandMessageProfileType extends MessageProfileType's Results."""
        grip = _children(write_component_profile(SAMPLE_RAW), "MessageProfile")[0]
        assert [etree.QName(e).localname for e in grip] == ["Results", "Arguments"]
        assert grip.get(f"{{{XSI_NS}}}type") == "rois:CommandMessageProfileType"
        assert grip.get(f"{{{ROIS_NS}}}timeout") == "500"

    def test_no_default_writes_no_attribute(self) -> None:
        speed, mode = _children(write_component_profile(SAMPLE_RAW), "ParameterProfile")
        assert f"{{{ROIS_NS}}}default_value" not in speed.attrib
        assert mode.get(f"{{{ROIS_NS}}}default_value") == "soft"

    def test_extensions_are_not_written(self) -> None:
        profile = SAMPLE_RAW.model_copy(
            update={
                "parameter_profiles": [
                    _param("speed", "int").model_copy(update={"read_only": True})
                ]
            }
        )
        xml = write_component_profile(profile)
        assert b"read_only" not in xml
        assert b"function" not in xml

    def test_omits_messages_of_a_resolved_sub_profile(self) -> None:
        registry = ProfileRegistry()
        common = HRIComponentProfile(
            identifier=RoISIdentifierType(authority="OMG", code="RoISCommon"),
            name="rois_common",
            command_profiles=[CommandMessageProfile(name="start")],
        )
        registry.add(common)
        full = read_component_profile(SAMPLE_PROFILE, registry=registry)
        xml = write_component_profile(full, registry=registry)
        names = [m.get(f"{{{ROIS_NS}}}name") for m in _children(xml, "MessageProfile")]
        assert "start" not in names
        assert read_component_profile(xml, registry=registry) == full


@requires_normative
class TestNormativeRoundTrip:
    @pytest.mark.parametrize("filename", PROFILE_FILES)
    def test_raw_round_trip(self, filename: str) -> None:
        profile = read_component_profile(NORMATIVE_DIR / filename)
        assert read_component_profile(write_component_profile(profile)) == profile

    @pytest.mark.parametrize("filename", PROFILE_FILES)
    def test_resolved_round_trip(self, filename: str) -> None:
        registry = _registry()
        profile = read_component_profile(NORMATIVE_DIR / filename, registry=registry)
        written = write_component_profile(profile, registry=registry)
        assert read_component_profile(written, registry=registry) == profile

    @pytest.mark.parametrize(
        "filename",
        [
            pytest.param(
                f,
                marks=pytest.mark.xfail(
                    reason="Validation row 9: the XSD has no Arguments on queries and events",
                    strict=True,
                ),
            )
            if f in XSD_GAP_FILES
            else f
            for f in PROFILE_FILES
        ],
    )
    def test_written_profile_validates(self, filename: str) -> None:
        schema = _schema()
        registry = _registry()
        profile = read_component_profile(NORMATIVE_DIR / filename, registry=registry)
        document = etree.fromstring(write_component_profile(profile, registry=registry))
        assert schema.validate(document), schema.error_log.last_error


# ---------------------------------------------------------------------------
# Engine profiles
# ---------------------------------------------------------------------------

SAMPLE_ENGINE = f"""<rois:HRIEngineProfile gml:id="main" {HEADER}>
  <gml:identifier codeSpace="urn:ietf:rfc:2141">urn:x-rois:def:HRIEngine:ACME::Main</gml:identifier>
  <gml:name>Main</gml:name>
  <rois:SubProfile gml:id="sub1">
    <gml:identifier codeSpace="urn:ietf:rfc:2141">{SUB1}</gml:identifier>
    <rois:HRIComponent>urn:x-rois:def:HRIComponent:ACME::PersonDetection</rois:HRIComponent>
  </rois:SubProfile>
  <rois:HRIComponent>urn:x-rois:def:HRIComponent:ACME::PersonDetection</rois:HRIComponent>
  <rois:HRIComponent>urn:x-rois:def:HRIComponent:ACME::Gripper</rois:HRIComponent>
  <rois:ParameterProfile rois:name="robot_name" rois:default_value="r1">
    <rois:data_type_ref rois:code="string"/>
  </rois:ParameterProfile>
</rois:HRIEngineProfile>
"""

ENGINE = HRIEngineProfileType(
    identifier=RoISIdentifierType(authority="ACME", code="Main"),
    name="Main",
    sub_profiles=[
        HRIEngineProfileType(
            identifier=RoISIdentifierType(authority="ACME", code="Sub1"),
            component_ids=["urn:x-rois:def:HRIComponent:ACME::PersonDetection"],
        )
    ],
    component_ids=[
        "urn:x-rois:def:HRIComponent:ACME::PersonDetection",
        "urn:x-rois:def:HRIComponent:ACME::Gripper",
    ],
    parameter_profiles=[
        ParameterProfile(name="robot_name", data_type_ref=_code("string"), default_value="r1")
    ],
)

DETECTION = SAMPLE_RAW.model_copy(
    update={
        "identifier": RoISIdentifierType(authority="ACME", code="PersonDetection"),
        "name": "person_detection",
    }
)


def _bundle_registry() -> ProfileRegistry:
    registry = ProfileRegistry()
    registry.add(SAMPLE_RAW)
    registry.add(DETECTION)
    return registry


class TestEngineProfile:
    def test_read(self) -> None:
        """Rows 5 and 6: engine parameters, HRIComponent refs kept as strings."""
        assert read_engine_profile(SAMPLE_ENGINE) == ENGINE

    def test_name_is_optional(self) -> None:
        doc = SAMPLE_ENGINE.replace("<gml:name>Main</gml:name>", "")
        assert read_engine_profile(doc).name is None

    def test_round_trip(self) -> None:
        assert read_engine_profile(write_engine_profile(ENGINE)) == ENGINE

    def test_holds_only_the_xsd_elements(self) -> None:
        root = etree.fromstring(write_engine_profile(ENGINE))
        assert etree.QName(root).localname == "HRIEngineProfile"
        assert [etree.QName(e).localname for e in root] == [
            "identifier",
            "name",
            "SubProfile",
            "HRIComponent",
            "HRIComponent",
            "ParameterProfile",
        ]

    def test_no_name_writes_no_gml_name(self) -> None:
        xml = write_engine_profile(ENGINE.model_copy(update={"name": None}))
        assert not _children(xml, "name")

    def test_every_profile_has_a_unique_gml_id(self) -> None:
        """Row 34: the root and every SubProfile carry their own gml:id."""
        sub = ENGINE.sub_profiles[0]
        engine = ENGINE.model_copy(update={"sub_profiles": [sub, sub]})
        root = etree.fromstring(write_engine_profile(engine))
        ids = [e.get(f"{{{GML_NS}}}id") for e in root.iter() if e.get(f"{{{GML_NS}}}id")]
        assert len(ids) == 3
        assert len(set(ids)) == 3


class TestEngineBundle:
    def test_one_document_per_referenced_component(self) -> None:
        bundle = write_engine_bundle(ENGINE, _bundle_registry())
        assert read_engine_profile(bundle.engine) == ENGINE
        assert set(bundle.components) == set(ENGINE.component_ids)
        gripper = bundle.components["urn:x-rois:def:HRIComponent:ACME::Gripper"]
        assert read_component_profile(gripper) == SAMPLE_RAW

    def test_gml_ids_derive_from_the_identifier(self) -> None:
        bundle = write_engine_bundle(ENGINE, _bundle_registry())
        ids = [
            etree.fromstring(doc).get(f"{{{GML_NS}}}id") for doc in bundle.components.values()
        ]
        assert sorted(ids) == ["ACME_Gripper", "ACME_PersonDetection"]

    def test_unknown_component_raises(self) -> None:
        with pytest.raises(UnresolvedProfileError):
            write_engine_bundle(ENGINE, ProfileRegistry())


# ---------------------------------------------------------------------------
# Command unit sequences
# ---------------------------------------------------------------------------


def _xml_unit(command_type: str, tag: str = "command_list") -> str:
    return (
        f'<rois:{tag} xsi:type="rois:CommandMessageType" rois:command_type="{command_type}" '
        f'rois:command_id=""><rois:component_ref rois:code="arm"/></rois:{tag}>'
    )


BRANCH_FORM = f"""<rois:CommandUnitSequence {HEADER}>
  {_xml_unit("A", "command_unit_list")}
  <rois:command_unit_list xsi:type="rois:ConcurrentCommandsType" rois:delay_time="10">
    <rois:branch_list xsi:type="rois:BranchType">{_xml_unit("C")}{_xml_unit("D")}</rois:branch_list>
    <rois:branch_list xsi:type="rois:BranchType">{_xml_unit("E")}</rois:branch_list>
  </rois:command_unit_list>
  {_xml_unit("F", "command_unit_list")}
</rois:CommandUnitSequence>
"""

FLAT_FORM = f"""<rois:CommandUnitSequence {HEADER}>
  <rois:command_unit_list xsi:type="rois:ConcurrentCommandsType">
    {_xml_unit("C")}{_xml_unit("E")}
  </rois:command_unit_list>
</rois:CommandUnitSequence>
"""


def _unit(command_type: str) -> CommandUnit:
    return CommandUnit(component_ref="arm", command_type=command_type, command_id="")


class TestCommandUnitSequence:
    def test_reads_the_branch_list_form(self) -> None:
        """Annex B.1: branches run in parallel, each in order."""
        assert read_command_unit_sequence(BRANCH_FORM) == CommandUnitSequence(
            command_unit_list=[
                _unit("A"),
                ConcurrentCommands(
                    delay_time=10,
                    branch_list=[
                        Branch(command_list=[_unit("C"), _unit("D")]),
                        Branch(command_list=[_unit("E")]),
                    ],
                ),
                _unit("F"),
            ]
        )

    def test_reads_the_flat_xsd_form_as_one_command_branches(self) -> None:
        sequence = read_command_unit_sequence(FLAT_FORM)
        group = sequence.command_unit_list[0]
        assert isinstance(group, ConcurrentCommands)
        assert group.branch_list == [
            Branch(command_list=[_unit("C")]),
            Branch(command_list=[_unit("E")]),
        ]

    def test_reads_branches_inside_command_list(self) -> None:
        """Formal Table 8-15: ConcurrentCommands' command list holds Branch elements."""
        typed = f"""<rois:CommandUnitSequence {HEADER}>
  <rois:command_unit_list xsi:type="rois:ConcurrentCommandsType">
    <rois:command_list xsi:type="rois:BranchType">
      {_xml_unit("C")}{_xml_unit("D")}
    </rois:command_list>
    <rois:command_list xsi:type="rois:BranchType">{_xml_unit("E")}</rois:command_list>
  </rois:command_unit_list>
</rois:CommandUnitSequence>
"""
        wrapped = f"""<rois:CommandUnitSequence {HEADER}>
  <rois:command_unit_list xsi:type="rois:ConcurrentCommandsType">
    <rois:command_list>
      <rois:Branch>{_xml_unit("C")}{_xml_unit("D")}</rois:Branch>
      <rois:Branch>{_xml_unit("E")}</rois:Branch>
    </rois:command_list>
  </rois:command_unit_list>
</rois:CommandUnitSequence>
"""
        expected = [
            Branch(command_list=[_unit("C"), _unit("D")]),
            Branch(command_list=[_unit("E")]),
        ]
        for doc in (typed, wrapped):
            group = read_command_unit_sequence(doc).command_unit_list[0]
            assert isinstance(group, ConcurrentCommands)
            assert group.branch_list == expected
            written = write_command_unit_sequence(CommandUnitSequence(command_unit_list=[group]))
            unit_list = _children(written, "command_unit_list")[0]
            assert [etree.QName(e).localname for e in unit_list] == ["branch_list", "branch_list"]

    def test_reads_the_20250801_namespace(self) -> None:
        doc = BRANCH_FORM.replace(
            f'xmlns:rois="{ROIS_NS}"', 'xmlns:rois="http://www.omg.org/spec/RoIS/20250801"'
        )
        assert read_command_unit_sequence(doc) == read_command_unit_sequence(BRANCH_FORM)

    def test_round_trip(self) -> None:
        sequence = read_command_unit_sequence(BRANCH_FORM)
        assert read_command_unit_sequence(write_command_unit_sequence(sequence)) == sequence

    def test_writes_one_command_branches_in_the_xsd_form(self) -> None:
        xml = write_command_unit_sequence(read_command_unit_sequence(FLAT_FORM))
        group = _children(xml, "command_unit_list")[0]
        assert [etree.QName(e).localname for e in group] == ["command_list", "command_list"]

    @requires_normative
    def test_xsd_form_validates(self) -> None:
        sequence = CommandUnitSequence(
            command_unit_list=[
                CommandUnit(
                    component_ref="arm",
                    command_type="grip",
                    command_id="c1",
                    delay_time=5,
                    arguments=[Argument(name="force", data_type_ref="int", value="3")],
                ),
                ConcurrentCommands(
                    branch_list=[
                        Branch(command_list=[_unit("C")]),
                        Branch(command_list=[_unit("E")]),
                    ]
                ),
            ]
        )
        schema = _schema()
        document = etree.fromstring(write_command_unit_sequence(sequence))
        assert schema.validate(document), schema.error_log.last_error


ANNEX_B2_SHAPE = f"""<rois:command_list {HEADER} xsi:type="rois:CommandMessageType"
    rois:command_type="set_parameter" rois:command_id="">
  <rois:component_ref rois:version="0.1" rois:codebook_ref="urn:example:codebook"
      rois:code="voice"/>
  <rois:arguments>
    <rois:parameter rois:name="speech_text">
      <rois:data_type_ref rois:code="string"/>
      <rois:value>good morning</rois:value>
    </rois:parameter>
    <rois:parameter rois:name="volume">
      <rois:data_type_ref rois:code="int"/>
      <rois:value>7</rois:value>
    </rois:parameter>
  </rois:arguments>
</rois:command_list>
"""


class TestCommandMessage:
    def test_reads_a_set_parameter_command(self) -> None:
        """Annex B.2: a set_parameter command message with an empty command_id."""
        assert read_command_message(ANNEX_B2_SHAPE) == CommandUnit(
            component_ref="voice",
            command_type="set_parameter",
            command_id="",
            arguments=[
                Argument(name="speech_text", data_type_ref="string", value="good morning"),
                Argument(name="volume", data_type_ref="int", value="7"),
            ],
        )
