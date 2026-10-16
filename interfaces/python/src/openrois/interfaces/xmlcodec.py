"""Read and write the RoIS XML forms of profiles and command unit sequences.

The OMG RoIS Framework 2.0 describes components and engines in XML (XML-Profiles.xsd,
Annex A) and the procedure of ``execute`` as a CommandUnitSequence (Annex B). This module
reads those documents into the Pydantic models of ``openrois.interfaces`` and writes the
models back.

- ``read_component_profile`` and ``write_component_profile``: an HRIComponentProfile.
  A ``ProfileRegistry`` resolves SubComponentProfile references: with a registry, the
  reader lists the messages of each sub-profile before the profile's own, and the
  writer leaves them out again.
- ``read_engine_profile`` and ``write_engine_profile``: an HRIEngineProfile with nested
  SubProfiles. ``write_engine_bundle`` adds one document per referenced component.
- ``read_command_unit_sequence`` and ``write_command_unit_sequence``: a
  CommandUnitSequence. ``read_command_message`` reads one command message (Annex B.2).

The reader uses lxml with no network access and no external entities, and fetches no
GML schema. Where the normative files and the XSD disagree, the codec follows the files
(docs/rois-reference.md, section 16): query and event profiles may carry Arguments, a
ConcurrentCommands group holds branches, HRIComponent references are plain strings, and
a RoIS namespace URI with surrounding whitespace is read as the RoIS namespace.

The OpenRoIS extensions ``HRIComponentProfile.function`` and
``ParameterProfile.read_only`` have no XML form and are not written.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from lxml import etree

from openrois.interfaces.hri import (
    Argument,
    Branch,
    CommandUnit,
    CommandUnitSequence,
    CommandUnitSequenceItem,
    ConcurrentCommands,
)
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

ROIS_NS = "http://www.omg.org/spec/RoIS/20240801"
"""The RoIS namespace of XML-Profiles.xsd, the one the codec writes."""

ROIS_NS_ALIASES = frozenset({"http://www.omg.org/spec/RoIS/20250801"})
"""Other spellings of the RoIS namespace the reader accepts. The published files sit under
/spec/RoIS/20250801/ but declare 20240801, and may later be aligned with their path."""

GML_NS = "http://www.opengis.net/gml/3.2"
"""The GML 3.2 namespace, for gml:id, gml:identifier and gml:name."""

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

CODE_SPACE = "urn:ietf:rfc:2141"
"""The codeSpace of every gml:identifier the codec writes: the URN syntax."""

COMPONENT_GML_ID = "component_profile"
"""The gml:id every normative component profile file uses."""

_NSMAP = {"rois": ROIS_NS, "gml": GML_NS, "xsi": XSI_NS}

type XmlSource = str | bytes | Path
"""An XML document: its text, its bytes, or the path of a file that holds it."""


class ProfileFormatError(ValueError):
    """The document is not well-formed XML or not the RoIS form the codec reads."""


class UnresolvedProfileError(LookupError):
    """A referenced profile is not in the registry."""


# ---------------------------------------------------------------------------
# URNs
# ---------------------------------------------------------------------------


def parse_urn(urn: str) -> RoISIdentifierType:
    """The identifier of a profile URN.

    ``urn:x-rois:def:component:OMG::Navigation`` gives authority ``OMG`` and code
    ``Navigation``. A URN without the ``::`` separator is kept whole as the code.
    """
    head, separator, code = urn.strip().rpartition("::")
    if not separator or not head or not code:
        return RoISIdentifierType(code=urn.strip())
    return RoISIdentifierType(authority=head.rsplit(":", 1)[-1], code=code)


def component_urn(identifier: RoISIdentifierType) -> str:
    """The URN of a component profile, as the normative files write it.

    An identifier without an authority is its code.
    """
    return _urn("component", identifier)


def _urn(kind: str, identifier: RoISIdentifierType) -> str:
    if not identifier.authority:
        return identifier.code
    return f"urn:x-rois:def:{kind}:{identifier.authority}::{identifier.code}"


def _key(reference: str | RoISIdentifierType) -> tuple[str, str]:
    identifier = parse_urn(reference) if isinstance(reference, str) else reference
    return identifier.authority, identifier.code


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ProfileRegistry:
    """Component profiles by identifier, for resolving SubComponentProfile references.

    A reference matches a profile by authority and code, so
    ``urn:x-rois:def:Component:OMG::RoISCommon`` (the spelling the normative files use
    for the reference) finds the profile whose identifier is OMG ``RoISCommon``.
    """

    def __init__(self, profiles: Iterable[HRIComponentProfile] = ()) -> None:
        self._profiles: dict[tuple[str, str], HRIComponentProfile] = {}
        for profile in profiles:
            self.add(profile)

    def add(self, profile: HRIComponentProfile) -> None:
        """Register a profile under its identifier, replacing one with the same key."""
        self._profiles[_key(profile.identifier)] = profile

    def get(self, reference: str | RoISIdentifierType) -> HRIComponentProfile:
        """The profile a URN or identifier names.

        Raises:
            UnresolvedProfileError: No registered profile has that identifier.
        """
        try:
            return self._profiles[_key(reference)]
        except KeyError:
            raise UnresolvedProfileError(f"No profile for {reference!r}") from None

    def load(self, source: XmlSource) -> HRIComponentProfile:
        """Read a component profile, resolved against this registry, and register it."""
        profile = read_component_profile(source, registry=self)
        self.add(profile)
        return profile

    def __contains__(self, reference: object) -> bool:
        if not isinstance(reference, (str, RoISIdentifierType)):
            return False
        return _key(reference) in self._profiles

    def __iter__(self) -> Iterator[HRIComponentProfile]:
        return iter(list(self._profiles.values()))

    def __len__(self) -> int:
        return len(self._profiles)


def resolve_profile(
    profile: HRIComponentProfile, registry: ProfileRegistry
) -> HRIComponentProfile:
    """The profile with the messages of its sub-profiles listed before its own.

    A message that a sub-profile already lists, equal in every field, is listed once.

    Raises:
        UnresolvedProfileError: A sub-profile is not in the registry.
    """
    commands: list[CommandMessageProfile] = []
    queries: list[QueryMessageProfile] = []
    events: list[EventMessageProfile] = []
    for reference in profile.sub_component_profiles:
        sub = registry.get(reference)
        _extend(commands, sub.command_profiles)
        _extend(queries, sub.query_profiles)
        _extend(events, sub.event_profiles)
    _extend(commands, profile.command_profiles)
    _extend(queries, profile.query_profiles)
    _extend(events, profile.event_profiles)
    return profile.model_copy(
        update={"command_profiles": commands, "query_profiles": queries, "event_profiles": events}
    )


def _extend[M: MessageProfile](target: list[M], messages: Iterable[M]) -> None:
    target.extend(m for m in messages if m not in target)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# libxml2 reports a namespace URI it cannot parse, such as one with a trailing space,
# as an error. The codec reads such a URI with the whitespace trimmed (row 36).
_TOLERATED_ERRORS = frozenset({"WAR_NS_URI", "WAR_NS_URI_RELATIVE"})


def _parse(source: XmlSource) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        remove_comments=True,
        remove_pis=True,
        recover=True,
        huge_tree=False,
    )
    try:
        if isinstance(source, Path):
            data = source.read_bytes()
        elif isinstance(source, str):
            data = source.encode("utf-8")
        else:
            data = source
        root = etree.fromstring(data, parser)
    except (etree.XMLSyntaxError, ValueError) as error:
        raise ProfileFormatError(f"Not well-formed XML: {error}") from error
    errors = [e for e in parser.error_log if e.type_name not in _TOLERATED_ERRORS]
    if root is None or any(e.level >= etree.ErrorLevels.ERROR for e in errors):
        detail = errors[0].message if errors else "empty document"
        raise ProfileFormatError(f"Not well-formed XML: {detail}")
    return root


def _canonical(namespace: str | None) -> str:
    """A namespace URI trimmed, with an alias of the RoIS namespace read as ROIS_NS."""
    trimmed = namespace.strip() if namespace else ""
    return ROIS_NS if trimmed in ROIS_NS_ALIASES else trimmed


def _namespace(element: etree._Element) -> str:
    return _canonical(etree.QName(element).namespace)


def _is(element: etree._Element, local: str, namespace: str = ROIS_NS) -> bool:
    return (
        isinstance(element.tag, str)
        and etree.QName(element).localname == local
        and _namespace(element) == namespace
    )


def _children(element: etree._Element, local: str, namespace: str = ROIS_NS) -> list[
    etree._Element
]:
    return [child for child in element if _is(child, local, namespace)]


def _child(element: etree._Element, local: str, namespace: str = ROIS_NS) -> etree._Element | None:
    found = _children(element, local, namespace)
    return found[0] if found else None


def _attr(element: etree._Element, local: str, namespace: str = ROIS_NS) -> str | None:
    """An attribute in the namespace, or unqualified for a RoIS attribute."""
    for key, value in element.attrib.items():
        name = etree.QName(key)
        if name.localname != local:
            continue
        attr_namespace = _canonical(name.namespace)
        if attr_namespace == namespace or (not attr_namespace and namespace == ROIS_NS):
            return str(value)
    return None


def _required(element: etree._Element, local: str) -> str:
    value = _attr(element, local)
    if value is None:
        raise ProfileFormatError(f"<{etree.QName(element).localname}> has no {local}")
    return value


def _integer(element: etree._Element, local: str) -> int | None:
    value = _attr(element, local)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        raise ProfileFormatError(f"{local}={value!r} is not an integer") from None


def _text(element: etree._Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _xsi_type(element: etree._Element) -> str:
    value = _attr(element, "type", XSI_NS) or ""
    return value.rpartition(":")[2]


def _expect(root: etree._Element, local: str) -> None:
    if not _is(root, local):
        raise ProfileFormatError(f"Expected rois:{local}, found {root.tag!r}")


def _identifier(element: etree._Element) -> RoISIdentifierType:
    identifier = _child(element, "identifier", GML_NS)
    if identifier is None or not _text(identifier):
        raise ProfileFormatError(f"<{etree.QName(element).localname}> has no gml:identifier")
    return parse_urn(_text(identifier))


def _identifier_ref(element: etree._Element) -> RoISIdentifierType:
    return RoISIdentifierType(
        authority=_attr(element, "authority") or "",
        code=_attr(element, "code") or "",
        codebook_ref=_attr(element, "codebook_ref") or "",
        version=_attr(element, "version") or "",
    )


# ---------------------------------------------------------------------------
# Reader: profiles
# ---------------------------------------------------------------------------


def read_component_profile(
    source: XmlSource, *, registry: ProfileRegistry | None = None
) -> HRIComponentProfile:
    """Read an HRIComponentProfile document.

    Args:
        source: The document: its text, its bytes, or the path of its file.
        registry: When given, SubComponentProfile references are resolved from it and
            the messages of each sub-profile are listed before the profile's own.

    Raises:
        ProfileFormatError: The document is not a component profile.
        UnresolvedProfileError: A sub-profile is not in the registry.
    """
    root = _parse(source)
    _expect(root, "HRIComponentProfile")
    profile = _component_profile(root)
    return resolve_profile(profile, registry) if registry is not None else profile


def _component_profile(element: etree._Element) -> HRIComponentProfile:
    commands: list[CommandMessageProfile] = []
    queries: list[QueryMessageProfile] = []
    events: list[EventMessageProfile] = []
    for child in element:
        kind = _message_kind(child)
        if kind == "command":
            commands.append(
                CommandMessageProfile(
                    name=_required(child, "name"),
                    results=_parameters(child, "Results"),
                    arguments=_parameters(child, "Arguments"),
                    timeout=_integer(child, "timeout"),
                )
            )
        elif kind == "query":
            queries.append(
                QueryMessageProfile(
                    name=_required(child, "name"),
                    results=_parameters(child, "Results"),
                    arguments=_parameters(child, "Arguments"),
                )
            )
        elif kind == "event":
            events.append(
                EventMessageProfile(
                    name=_required(child, "name"),
                    results=_parameters(child, "Results"),
                    arguments=_parameters(child, "Arguments"),
                )
            )
    return HRIComponentProfile(
        identifier=_identifier(element),
        name=_text(_child(element, "name", GML_NS)),
        sub_component_profiles=[
            _text(sub) for sub in _children(element, "SubComponentProfile") if _text(sub)
        ],
        command_profiles=commands,
        query_profiles=queries,
        event_profiles=events,
        parameter_profiles=_parameters(element, "ParameterProfile"),
    )


# Message profiles by xsi:type, and by the element names of the substitution group.
_MESSAGE_TYPES = MappingProxyType(
    {
        "CommandMessageProfileType": "command",
        "QueryMessageProfileType": "query",
        "EventMessageProfileType": "event",
    }
)
_MESSAGE_ELEMENTS = MappingProxyType(
    {
        "CommandMessageProfile": "command",
        "QueryMessageProfile": "query",
        "EventMessageProfile": "event",
    }
)


def _message_kind(element: etree._Element) -> str | None:
    if not isinstance(element.tag, str) or _namespace(element) != ROIS_NS:
        return None
    local = etree.QName(element).localname
    if local in _MESSAGE_ELEMENTS:
        return _MESSAGE_ELEMENTS[local]
    if local != "MessageProfile":
        return None
    xsi_type = _xsi_type(element)
    if xsi_type not in _MESSAGE_TYPES:
        name = _attr(element, "name")
        raise ProfileFormatError(f"Message profile {name!r} has the unknown type {xsi_type!r}")
    return _MESSAGE_TYPES[xsi_type]


def _parameters(element: etree._Element, local: str) -> list[ParameterProfile]:
    return [_parameter(child) for child in _children(element, local)]


def _parameter(element: etree._Element) -> ParameterProfile:
    data_type = _child(element, "data_type_ref")
    if data_type is None:
        raise ProfileFormatError(f"Parameter {_attr(element, 'name')!r} has no data_type_ref")
    return ParameterProfile(
        name=_required(element, "name"),
        data_type_ref=_identifier_ref(data_type),
        default_value=_attr(element, "default_value"),
        description=_attr(element, "description") or "",
    )


def read_engine_profile(source: XmlSource) -> HRIEngineProfileType:
    """Read an HRIEngineProfile document.

    HRIComponent references are kept as strings: the XSD types them xsd:ID, which the
    URNs of Annex A.4 cannot satisfy (validation row 6).

    Raises:
        ProfileFormatError: The document is not an engine profile.
    """
    root = _parse(source)
    _expect(root, "HRIEngineProfile")
    return _engine_profile(root)


def _engine_profile(element: etree._Element) -> HRIEngineProfileType:
    name = _child(element, "name", GML_NS)
    return HRIEngineProfileType(
        identifier=_identifier(element),
        name=_text(name) if name is not None else None,
        sub_profiles=[_engine_profile(sub) for sub in _children(element, "SubProfile")],
        component_ids=[_text(c) for c in _children(element, "HRIComponent") if _text(c)],
        parameter_profiles=_parameters(element, "ParameterProfile"),
    )


# ---------------------------------------------------------------------------
# Writer: profiles
# ---------------------------------------------------------------------------


def _rois(local: str) -> str:
    return f"{{{ROIS_NS}}}{local}"


def _gml(local: str) -> str:
    return f"{{{GML_NS}}}{local}"


def _xsi(local: str) -> str:
    return f"{{{XSI_NS}}}{local}"


def _root(local: str) -> etree._Element:
    return etree.Element(_rois(local), nsmap=_NSMAP)


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _write_identity(
    element: etree._Element, gml_id: str, urn: str, name: str | None
) -> None:
    element.set(_gml("id"), gml_id)
    identifier = etree.SubElement(element, _gml("identifier"))
    identifier.set("codeSpace", CODE_SPACE)
    identifier.text = urn
    if name is not None:
        etree.SubElement(element, _gml("name")).text = name


def write_component_profile(
    profile: HRIComponentProfile,
    *,
    registry: ProfileRegistry | None = None,
    gml_id: str = COMPONENT_GML_ID,
) -> bytes:
    """Write an HRIComponentProfile document.

    Args:
        profile: The profile to write.
        registry: When given, a message that a resolvable sub-profile already lists is
            left out, so a profile read with a registry is written as its file was.
        gml_id: The gml:id of the profile element.

    Returns:
        The UTF-8 document, with an XML declaration.
    """
    root = _root("HRIComponentProfile")
    _write_component(root, profile, registry, gml_id)
    return _serialize(root)


def _write_component(
    element: etree._Element,
    profile: HRIComponentProfile,
    registry: ProfileRegistry | None,
    gml_id: str,
) -> None:
    _write_identity(element, gml_id, component_urn(profile.identifier), profile.name)
    inherited = _inherited(profile, registry)
    for reference in profile.sub_component_profiles:
        etree.SubElement(element, _rois("SubComponentProfile")).text = reference
    for command in profile.command_profiles:
        if command not in inherited.command_profiles:
            message = _write_message(element, command, "CommandMessageProfileType")
            if command.timeout is not None:
                message.set(_rois("timeout"), str(command.timeout))
            # XSD order: Results come from MessageProfileType, Arguments from the extension.
            _write_parameters(message, "Results", command.results)
            _write_parameters(message, "Arguments", command.arguments)
    for query in profile.query_profiles:
        if query not in inherited.query_profiles:
            message = _write_message(element, query, "QueryMessageProfileType")
            _write_parameters(message, "Arguments", query.arguments)
            _write_parameters(message, "Results", query.results)
    for event in profile.event_profiles:
        if event not in inherited.event_profiles:
            message = _write_message(element, event, "EventMessageProfileType")
            _write_parameters(message, "Arguments", event.arguments)
            _write_parameters(message, "Results", event.results)
    _write_parameters(element, "ParameterProfile", profile.parameter_profiles)


def _inherited(
    profile: HRIComponentProfile, registry: ProfileRegistry | None
) -> HRIComponentProfile:
    """The messages the resolvable sub-profiles of a profile list."""
    empty = profile.model_copy(
        update={"command_profiles": [], "query_profiles": [], "event_profiles": []}
    )
    if registry is None:
        return empty
    resolvable = [ref for ref in profile.sub_component_profiles if ref in registry]
    subs = empty.model_copy(update={"sub_component_profiles": resolvable})
    return resolve_profile(subs, registry)


def _write_message(
    parent: etree._Element, message: MessageProfile, xsi_type: str
) -> etree._Element:
    element = etree.SubElement(parent, _rois("MessageProfile"))
    element.set(_rois("name"), message.name)
    element.set(_xsi("type"), f"rois:{xsi_type}")
    return element


def _write_parameters(
    parent: etree._Element, local: str, parameters: Sequence[ParameterProfile]
) -> None:
    for parameter in parameters:
        element = etree.SubElement(parent, _rois(local))
        element.set(_rois("name"), parameter.name)
        if parameter.default_value is not None:
            element.set(_rois("default_value"), parameter.default_value)
        if parameter.description:
            element.set(_rois("description"), parameter.description)
        _write_identifier_ref(element, "data_type_ref", parameter.data_type_ref)


def _write_identifier_ref(
    parent: etree._Element, local: str, identifier: RoISIdentifierType
) -> None:
    element = etree.SubElement(parent, _rois(local))
    for attribute in ("authority", "code", "codebook_ref", "version"):
        value = getattr(identifier, attribute)
        if value or attribute == "code":
            element.set(_rois(attribute), value)


def _gml_id(identifier: RoISIdentifierType, used: set[str]) -> str:
    """A gml:id derived from an identifier, unique among ``used``."""
    raw = f"{identifier.authority}_{identifier.code}" if identifier.authority else identifier.code
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)
    if not base or not (base[0].isalpha() or base[0] == "_"):
        base = f"_{base}"
    candidate, counter = base, 1
    while candidate in used:
        counter += 1
        candidate = f"{base}_{counter}"
    used.add(candidate)
    return candidate


def write_engine_profile(profile: HRIEngineProfileType) -> bytes:
    """Write an HRIEngineProfile document.

    The document holds what the XSD defines: gml:identifier, gml:name when the profile
    has one, the SubProfiles, the HRIComponent references and the ParameterProfiles.
    Every profile element gets a gml:id derived from its identifier, unique in the
    document (row 34).
    """
    return _serialize(_engine_element(profile, set()))


def _engine_element(profile: HRIEngineProfileType, used: set[str]) -> etree._Element:
    root = _root("HRIEngineProfile")
    _write_engine(root, profile, used)
    return root


def _write_engine(
    element: etree._Element, profile: HRIEngineProfileType, used: set[str]
) -> None:
    _write_identity(
        element,
        _gml_id(profile.identifier, used),
        _urn("HRIEngine", profile.identifier),
        profile.name,
    )
    for sub in profile.sub_profiles:
        _write_engine(etree.SubElement(element, _rois("SubProfile")), sub, used)
    for component in profile.component_ids:
        etree.SubElement(element, _rois("HRIComponent")).text = component
    _write_parameters(element, "ParameterProfile", profile.parameter_profiles)


@dataclass(frozen=True, slots=True)
class EngineBundle:
    """An engine profile document and the profile document of each component it names.

    Attributes:
        engine: The HRIEngineProfile document.
        components: One HRIComponentProfile document per referenced component, keyed by
            the reference as the engine profile writes it.
    """

    engine: bytes
    components: Mapping[str, bytes]


def write_engine_bundle(
    profile: HRIEngineProfileType, registry: ProfileRegistry
) -> EngineBundle:
    """Write an engine profile and a document for every component it references.

    The XSD has no place for a component profile inside an engine profile, so each
    component profile is a document of its own. Every gml:id in the bundle is derived
    from its profile's identifier and is unique across the bundle.

    Raises:
        UnresolvedProfileError: A referenced component is not in the registry.
    """
    used: set[str] = set()
    engine = _serialize(_engine_element(profile, used))
    components: dict[str, bytes] = {}
    for reference in _component_refs(profile):
        if reference in components:
            continue
        component = registry.get(reference)
        components[reference] = write_component_profile(
            component, registry=registry, gml_id=_gml_id(component.identifier, used)
        )
    return EngineBundle(engine=engine, components=MappingProxyType(components))


def _component_refs(profile: HRIEngineProfileType) -> Iterator[str]:
    yield from profile.component_ids
    for sub in profile.sub_profiles:
        yield from _component_refs(sub)


# ---------------------------------------------------------------------------
# Command unit sequences
# ---------------------------------------------------------------------------


def read_command_unit_sequence(source: XmlSource) -> CommandUnitSequence:
    """Read a CommandUnitSequence document.

    A ConcurrentCommands unit may hold the branch_list of Annex B.1, each branch an
    ordered command_list, or the flat command_list of the XSD, read as one-command
    branches (validation row 3). A command_list that holds a branch, the form formal
    Table 8-15 names, is read as that branch.

    Raises:
        ProfileFormatError: The document is not a command unit sequence.
    """
    root = _parse(source)
    _expect(root, "CommandUnitSequence")
    return CommandUnitSequence(
        command_unit_list=[_unit_list_item(e) for e in _children(root, "command_unit_list")]
    )


def read_command_message(source: XmlSource) -> CommandUnit:
    """Read one command message, a CommandMessageType element (Annex B.2).

    The component_ref keeps its code. An absent command_id reads as empty: the engine
    assigns it.
    """
    return _command_unit(_parse(source))


def _unit_list_item(element: etree._Element) -> CommandUnitSequenceItem:
    xsi_type = _xsi_type(element)
    if xsi_type == "ConcurrentCommandsType":
        return _concurrent(element)
    if xsi_type in ("CommandMessageType", ""):
        return _command_unit(element)
    raise ProfileFormatError(f"Unknown command unit type {xsi_type!r}")


def _concurrent(element: etree._Element) -> ConcurrentCommands:
    branches = _children(element, "branch_list")
    flat = _children(element, "command_list")
    if branches and flat:
        raise ProfileFormatError("ConcurrentCommands holds both branch_list and command_list")
    if branches:
        branch_list = [
            Branch(command_list=[_command_unit(c) for c in _children(b, "command_list")])
            for b in branches
        ]
    else:
        branch_list = [branch for child in flat for branch in _flat_item(child)]
    return ConcurrentCommands(branch_list=branch_list, delay_time=_integer(element, "delay_time"))


def _flat_item(element: etree._Element) -> list[Branch]:
    """The branches one command_list child of ConcurrentCommands stands for.

    In the XSD form it is a command, a one-command branch. Formal Table 8-15 types the
    list as Branch, so it may also be a branch (xsi:type BranchType, or no command_type
    and commands inside) or hold Branch elements.
    """
    wrapped = _children(element, "Branch")
    if wrapped:
        return [
            Branch(command_list=[_command_unit(c) for c in _children(b, "command_list")])
            for b in wrapped
        ]
    commands = _children(element, "command_list")
    if _xsi_type(element) == "BranchType" or (commands and _attr(element, "command_type") is None):
        return [Branch(command_list=[_command_unit(c) for c in commands])]
    return [Branch(command_list=[_command_unit(element)])]


def _command_unit(element: etree._Element) -> CommandUnit:
    component = _child(element, "component_ref")
    arguments = _child(element, "arguments")
    return CommandUnit(
        component_ref=(_attr(component, "code") or "") if component is not None else "",
        command_type=_required(element, "command_type"),
        command_id=_attr(element, "command_id") or "",
        arguments=[_argument(p) for p in _children(arguments, "parameter")]
        if arguments is not None
        else [],
        delay_time=_integer(element, "delay_time"),
    )


def _argument(element: etree._Element) -> Argument:
    data_type = _child(element, "data_type_ref")
    value = _child(element, "value")
    return Argument(
        name=_required(element, "name"),
        data_type_ref=(_attr(data_type, "code") or "") if data_type is not None else "",
        value=(value.text or "") if value is not None else "",
    )


def write_command_unit_sequence(sequence: CommandUnitSequence) -> bytes:
    """Write a CommandUnitSequence document in the XSD form.

    A ConcurrentCommands group whose branches each hold one command is written as the
    flat command_list of the XSD. The XSD cannot express a branch of several commands,
    so a group that has one is written with the branch_list of Annex B.1.
    """
    root = _root("CommandUnitSequence")
    for item in sequence.command_unit_list:
        element = etree.SubElement(root, _rois("command_unit_list"))
        if isinstance(item, ConcurrentCommands):
            _write_concurrent(element, item)
        else:
            _write_command_unit(element, item)
    return _serialize(root)


def _write_concurrent(element: etree._Element, group: ConcurrentCommands) -> None:
    element.set(_xsi("type"), "rois:ConcurrentCommandsType")
    if group.delay_time is not None:
        element.set(_rois("delay_time"), str(group.delay_time))
    if all(len(branch.command_list) == 1 for branch in group.branch_list):
        for branch in group.branch_list:
            _write_command_unit(
                etree.SubElement(element, _rois("command_list")), branch.command_list[0]
            )
        return
    for branch in group.branch_list:
        branch_element = etree.SubElement(element, _rois("branch_list"))
        branch_element.set(_xsi("type"), "rois:BranchType")
        for unit in branch.command_list:
            _write_command_unit(etree.SubElement(branch_element, _rois("command_list")), unit)


def _write_command_unit(element: etree._Element, unit: CommandUnit) -> None:
    element.set(_xsi("type"), "rois:CommandMessageType")
    if unit.delay_time is not None:
        element.set(_rois("delay_time"), str(unit.delay_time))
    element.set(_rois("command_id"), unit.command_id)
    element.set(_rois("command_type"), unit.command_type)
    _write_identifier_ref(element, "component_ref", RoISIdentifierType(code=unit.component_ref))
    if unit.arguments:
        arguments = etree.SubElement(element, _rois("arguments"))
        for argument in unit.arguments:
            parameter = etree.SubElement(arguments, _rois("parameter"))
            parameter.set(_rois("name"), argument.name)
            _write_identifier_ref(
                parameter, "data_type_ref", RoISIdentifierType(code=argument.data_type_ref)
            )
            etree.SubElement(parameter, _rois("value")).text = argument.value


__all__ = [
    "CODE_SPACE",
    "COMPONENT_GML_ID",
    "GML_NS",
    "ROIS_NS",
    "ROIS_NS_ALIASES",
    "XSI_NS",
    "EngineBundle",
    "ProfileFormatError",
    "ProfileRegistry",
    "UnresolvedProfileError",
    "XmlSource",
    "component_urn",
    "parse_urn",
    "read_command_message",
    "read_command_unit_sequence",
    "read_component_profile",
    "read_engine_profile",
    "resolve_profile",
    "write_command_unit_sequence",
    "write_component_profile",
    "write_engine_bundle",
    "write_engine_profile",
]
