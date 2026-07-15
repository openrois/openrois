"""Core HRI types derived from RoIS_HRI.idl.

This module maps the OMG RoIS Framework 2.0 HRI IDL types to Python Pydantic
models. These are the fundamental data types used across all RoIS interfaces:
SystemIF, CommandIF, QueryIF, and EventIF.

Source: OMG RoIS Framework 2.0-beta2, RoIS_HRI.idl and RoIS_HRI.hpp

Design decisions:
  - ReturnCode is a string enum for JSON readability.
  - RoIS_Identifier, Condition_t, HRI_Engine_Profile, DateTime, and Integer
    are type aliases (not new classes) — they carry semantic meaning without
    runtime overhead.
  - Result, Parameter, and Argument are Pydantic models with a `value` field
    typed as `str` (matching the HPP `std::string` and XSD `xsd:string`).
    Component-specific typed models provide structured typing where needed.
  - CommandUnitSequence is modelled as a structured Pydantic model (from the
    XSD CommandUnitSequenceType), not as a raw string (as the IDL typedefs it).
    The IDL `string` is the wire serialization format; the structured model is
    the in-memory representation.
  - RoLo::Architecture::Data is typedef'd to `string` in the IDL, so we
    alias it as `RoLoData = str` for clarity.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ReturnCode(StrEnum):
    """Return code for all RoIS operations.

    Maps to RoIS_HRI::ReturnCode_t in the IDL.
    """

    OK = "OK"
    ERROR = "ERROR"
    BAD_PARAMETER = "BAD_PARAMETER"
    UNSUPPORTED = "UNSUPPORTED"
    OUT_OF_RESOURCES = "OUT_OF_RESOURCES"
    TIMEOUT = "TIMEOUT"


class CommandType(StrEnum):
    """Command operation type for RoIS commands.

    Not an IDL enum — the IDL uses plain `string` for command_type. OpenRoIS
    defines this enum for compile-time safety. The wire values match the
    RoIS_Common::Command method names plus `set_parameter` and `execute`.
    """

    START = "start"
    STOP = "stop"
    SUSPEND = "suspend"
    RESUME = "resume"
    SET_PARAMETER = "set_parameter"
    EXECUTE = "execute"


# ---------------------------------------------------------------------------
# Type aliases — semantic wrappers over primitive types
# ---------------------------------------------------------------------------

# RoIS_HRI::RoIS_Identifier → string
# Unique identifier for a component, sub-engine, or other RoIS entity.
type RoISIdentifier = str

# RoIS_HRI::RoIS_IdentifierList → sequence<RoIS_Identifier>
# Ordered list of RoIS identifiers (e.g., component_ref_list from search()).
type RoISIdentifierList = list[RoISIdentifier]

# RoIS_HRI::Condition_t → string (ISO 19143 filter expression)
# ISO 19143 filter expression used by search(), query(), subscribe(), etc.
# Parsed and evaluated gateway-side; stored as an opaque string in the type system.
type ConditionT = str

# RoIS_HRI::HRI_Engine_Profile → string
# XML profile document describing an HRI Engine's capabilities.
# Returned by get_profile(); stored as a string (XML or JSON representation).
type HRIEngineProfile = str

# RoIS_HRI::DateTime → string (ISO 8601)
# ISO 8601 datetime string (e.g., '2025-01-15T10:30:00Z').
type DateTime = str

# RoIS_HRI::Integer → long
# 32-bit integer, matching the IDL 'long' type.
type Integer = int

# RoLo::Architecture::Data → string
# Positional or measurement data from the RoLo Architecture module.
# The IDL typedefs this to `string`; it carries structured data (e.g., coordinates)
# that is parsed by the component. Typed component models may provide structured
# representations.
type RoLoData = str

# OpenRoIS semantic aliases (not IDL typedefs — the IDL uses plain `string` for
# these, but we add named types for clarity and cross-language consistency).

# Query operation name, e.g. 'component_status', 'robot_position'.
type QueryType = str

# Event type name, e.g. 'person_detected', 'reached_target'.
type EventType = str

# Identifier returned by subscribe() and carried in event envelopes.
type SubscribeId = str

# Identifier returned by invoke() for long-running commands.
type CommandId = str


# ---------------------------------------------------------------------------
# Struct models — the core data carriers
# ---------------------------------------------------------------------------


class Result(BaseModel):
    """A named result value returned by query or event operations.

    Maps to RoIS_HRI::Result in the IDL.

    Attributes:
        name: The result parameter name (e.g., 'number', 'timestamp').
        data_type_ref: Reference to the data type (e.g., 'int', 'DateTime').
        value: The result value as a string. Component-specific typed models
            provide structured access.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    data_type_ref: RoISIdentifier
    value: str


class Parameter(BaseModel):
    """A named parameter for command operations (set_parameter, execute).

    Maps to RoIS_HRI::Parameter in the IDL.

    Attributes:
        name: The parameter name (e.g., 'target_position', 'time_limit').
        data_type_ref: Reference to the data type.
        value: The parameter value as a string.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    data_type_ref: RoISIdentifier
    value: str


class Argument(BaseModel):
    """A named argument for command execution.

    Maps to RoIS_HRI::Argument in the IDL.

    Attributes:
        name: The argument name.
        data_type_ref: Reference to the data type.
        value: The argument value as a string.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    data_type_ref: RoISIdentifier
    value: str


# ---------------------------------------------------------------------------
# List types
# ---------------------------------------------------------------------------

# Ordered list of Result values.
type ResultList = list[Result]

# Ordered list of Parameter values.
type ParameterList = list[Parameter]

# Ordered list of Argument values.
type ArgumentList = list[Argument]


# ---------------------------------------------------------------------------
# CommandUnitSequence — structured command execution model
# ---------------------------------------------------------------------------


class CommandUnit(BaseModel):
    """A single command within a CommandUnitSequence.

    Maps to CommandMessageType in XML-Profiles.xsd (CommandBaseType subtype).

    Attributes:
        component_ref: The component to send the command to.
        command_type: The command operation (e.g., 'start', 'stop',
            'set_parameter', 'execute').
        command_id: Unique identifier for this command instance.
        arguments: Optional list of arguments for the command.
        delay_time: Optional delay in milliseconds before executing this command.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    component_ref: RoISIdentifier
    command_type: CommandType = Field(
        description="Command operation: start, stop, suspend, resume, set_parameter, execute"
    )
    command_id: CommandId = Field(description="Unique command instance identifier")
    arguments: ArgumentList = Field(default_factory=list)
    delay_time: Integer | None = Field(default=None, description="Delay in ms before execution")


class ConcurrentCommands(BaseModel):
    """A group of commands to be executed concurrently.

    Maps to ConcurrentCommandsType in XML-Profiles.xsd.

    Attributes:
        command_list: The commands to execute in parallel.
        delay_time: Optional delay in milliseconds before executing this group.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_list: list[CommandUnit]
    delay_time: Integer | None = Field(default=None, description="Delay in ms before execution")


# A single item in a CommandUnitSequence — either a CommandUnit or a ConcurrentCommands group.
type CommandUnitSequenceItem = CommandUnit | ConcurrentCommands


class CommandUnitSequence(BaseModel):
    """An ordered sequence of command units (sequential and/or concurrent).

    Maps to CommandUnitSequenceType in XML-Profiles.xsd. The IDL typedefs this
    as `string`, but the XSD defines a rich structure with sequential and
    concurrent branches. We model the structured form; the string representation
    is the wire serialization format.

    Attributes:
        command_unit_list: Ordered list of command units and/or concurrent groups.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    command_unit_list: list[CommandUnitSequenceItem] = Field(
        description="Ordered sequence of command units (sequential) and concurrent groups",
    )
