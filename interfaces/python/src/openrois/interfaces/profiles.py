"""Component profile schema models derived from XML-Profiles.xsd.

This module maps the XSD profile types that describe RoIS component capabilities,
parameters, and message signatures. These models represent the structure found
in XML profile files like PersonDetection.xml, Navigation.xml, etc.

Source: OMG RoIS Framework 2.0-beta2, XML-Profiles.xsd
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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

    Maps to HRIComponentProfileType in XML-Profiles.xsd.

    Attributes:
        identifier: The component's structured identifier (URN).
        name: A short human-readable name (e.g., 'person_detecter').
        sub_component_profiles: URNs of sub-component profiles (e.g., RoISCommon).
        command_profiles: Command message profiles this component supports.
        query_profiles: Query message profiles this component supports.
        event_profiles: Event message profiles this component supports.
        parameter_profiles: Parameter declarations for this component.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    identifier: RoISIdentifierType
    name: str
    sub_component_profiles: list[str] = Field(default_factory=list)
    command_profiles: list[CommandMessageProfile] = Field(default_factory=list)
    query_profiles: list[QueryMessageProfile] = Field(default_factory=list)
    event_profiles: list[EventMessageProfile] = Field(default_factory=list)
    parameter_profiles: list[ParameterProfile] = Field(default_factory=list)


class HRIEngineProfileType(BaseModel):
    """Describes an HRI Engine's composition of sub-engines and components.

    Maps to HRIEngineProfileType in XML-Profiles.xsd.

    Attributes:
        identifier: The engine's structured identifier.
        sub_profiles: Nested sub-engine profiles.
        component_ids: IDs of components hosted by this engine.
        component_profiles: Full capability profiles for each component.
            Populated from adapter registration data. Optional (default
            empty) for backward compatibility with engines that only
            return component_ids.
        parameter_profiles: Engine-level parameter declarations.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    identifier: RoISIdentifierType
    sub_profiles: list[HRIEngineProfileType] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    component_profiles: list[HRIComponentProfile] = Field(default_factory=list)
    parameter_profiles: list[ParameterProfile] = Field(default_factory=list)
