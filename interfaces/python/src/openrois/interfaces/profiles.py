"""Component profile schema models derived from XML-Profiles.xsd.

This module maps the XSD profile types that describe RoIS component capabilities,
parameters, and message signatures. These models represent the structure found
in XML profile files like PersonDetection.xml, Navigation.xml, etc.

Source: OMG RoIS Framework 2.0, XML-Profiles.xsd
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Component function (from the RoSO ontology)
# ---------------------------------------------------------------------------


class ComponentFunction(StrEnum):
    """The RoSO function class of a component.

    Not part of XML-Profiles.xsd. The values are the Robotic Service Function
    Ontology classes that the spec's ontology file assigns to the basic components:
    Navigation, Reaction and SpeechSynthesis are Actuation, the detection,
    localization and recognition components are Sensing, and AudioStreaming is the
    generic Function class. An engine requires a bind before commands on an
    actuation component.

    ACTUATION: The component acts on the world (moves, speaks, shows).
    SENSING: The component observes the world.
    FUNCTION: The component is neither, for example a stream.
    """

    ACTUATION = "actuation"
    SENSING = "sensing"
    FUNCTION = "function"

# ---------------------------------------------------------------------------
# RoIS Identifier type (from XSD: RoISIdentifierType)
# ---------------------------------------------------------------------------


class RoISIdentifierType(BaseModel):
    """A structured RoIS identifier with optional metadata.

    Maps to RoISIdentifierType in XML-Profiles.xsd.

    Attributes:
        authority: Optional naming authority (e.g., 'OMG').
        code: The identifier code (e.g., 'PersonDetection').
        codebook_ref: Optional reference to a codebook or ontology.
        version: Optional version string.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    authority: str = ""
    code: str
    codebook_ref: str = ""
    version: str = ""


# ---------------------------------------------------------------------------
# Parameter profile types
# ---------------------------------------------------------------------------


class ParameterProfile(BaseModel):
    """Describes a parameter's data type and metadata.

    Maps to ParameterProfileType in XML-Profiles.xsd.

    Used in both message profiles (Arguments/Results) and component-level
    parameter declarations.

    Attributes:
        name: The parameter name.
        data_type_ref: Reference to the data type (e.g., 'int', 'DateTime',
            'RoISIdentifier[]').
        default_value: Optional default value as a string.
        description: Optional human-readable description.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    data_type_ref: RoISIdentifierType
    default_value: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Message profile types
# ---------------------------------------------------------------------------


class MessageProfile(BaseModel):
    """Base message profile describing a command, query, or event message.

    Maps to MessageProfileType in XML-Profiles.xsd.

    Attributes:
        name: The message name (e.g., 'person_detected', 'set_parameter').
        results: The result parameters of this message.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    results: list[ParameterProfile] = Field(default_factory=list)


class CommandMessageProfile(MessageProfile):
    """A command message profile with arguments and optional timeout.

    Maps to CommandMessageProfileType in XML-Profiles.xsd.

    Attributes:
        arguments: The input arguments for this command.
        timeout: Optional timeout in milliseconds.
    """

    arguments: list[ParameterProfile] = Field(default_factory=list)
    timeout: int | None = None


class QueryMessageProfile(MessageProfile):
    """A query message profile.

    Maps to QueryMessageProfileType in XML-Profiles.xsd.

    Queries have results but no arguments (the query_type and condition
    are passed separately, not as message arguments).
    """

    pass


class EventMessageProfile(MessageProfile):
    """An event message profile.

    Maps to EventMessageProfileType in XML-Profiles.xsd.

    Events have results (the event payload) but no arguments.
    """

    pass


# ---------------------------------------------------------------------------
# Component profile types
# ---------------------------------------------------------------------------


class HRIComponentProfile(BaseModel):
    """Describes a RoIS component's capabilities, messages, and parameters.

    Maps to HRIComponentProfileType in XML-Profiles.xsd. One profile describes one
    component instance: its messages are the ones that instance supports.

    Attributes:
        identifier: The component type, for example authority 'OMG' and code
            'PersonDetection' for urn:x-rois:def:component:OMG::PersonDetection.
        name: A short human-readable name (e.g., 'person_detecter').
        function: The RoSO function class. An OpenRoIS extension: the XSD has no
            such element.
        sub_component_profiles: URNs of sub-component profiles (e.g., RoISCommon).
        command_profiles: Command message profiles this component supports.
        query_profiles: Query message profiles this component supports.
        event_profiles: Event message profiles this component supports.
        parameter_profiles: Parameter declarations for this component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    identifier: RoISIdentifierType
    name: str
    function: ComponentFunction | None = Field(
        default=None,
        description="RoSO function class (OpenRoIS extension)",
    )
    sub_component_profiles: list[str] = Field(default_factory=list)
    command_profiles: list[CommandMessageProfile] = Field(default_factory=list)
    query_profiles: list[QueryMessageProfile] = Field(default_factory=list)
    event_profiles: list[EventMessageProfile] = Field(default_factory=list)
    parameter_profiles: list[ParameterProfile] = Field(default_factory=list)


class HRIEngineProfileType(BaseModel):
    """Describes an HRI Engine's composition of sub-engines and components.

    Maps to HRIEngineProfileType in XML-Profiles.xsd, field for field. The profile
    names its components by ref only, as the XSD does. The get_profile result carries
    their HRIComponentProfiles next to it.

    Attributes:
        identifier: The engine's structured identifier.
        sub_profiles: One profile per child engine (XSD SubProfile).
        component_ids: Fully qualified refs of every component reachable through this
            engine, including the components of its child engines (XSD HRIComponent).
        parameter_profiles: Engine-level parameter declarations.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    identifier: RoISIdentifierType
    sub_profiles: list[HRIEngineProfileType] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    parameter_profiles: list[ParameterProfile] = Field(default_factory=list)
