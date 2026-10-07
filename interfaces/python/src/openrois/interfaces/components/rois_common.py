"""The RoIS_Common profile, which the basic components include.

Derived from:
  - OMG RoIS Framework 2.0, RoISCommon.xml
  - OMG RoIS Framework 2.0, RoIS_Common.idl

Profile URN: urn:x-rois:def:Component:OMG::RoISCommon

RoIS_Common holds the messages that every basic component except SystemInformation
includes: the start, stop, suspend and resume commands and the component_status
query. A component profile names it in its sub_component_profiles, and the profile
constants of the basic components list its messages with their own.
"""

from __future__ import annotations

from openrois.interfaces.profiles import (
    CommandMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)

# ---------------------------------------------------------------------------
# Profile identifier
# ---------------------------------------------------------------------------

ROIS_COMMON_URN = "urn:x-rois:def:Component:OMG::RoISCommon"
"""URN of the RoIS_Common profile, as the XML profiles write it in SubComponentProfile."""


# ---------------------------------------------------------------------------
# Builders for the basic component profiles
# ---------------------------------------------------------------------------


def omg_identifier(code: str) -> RoISIdentifierType:
    """The identifier of a profile that OMG defines, for example ``Navigation``."""
    return RoISIdentifierType(authority="OMG", code=code)


def parameter(
    name: str,
    code: str,
    description: str = "",
    default_value: str = "",
) -> ParameterProfile:
    """A parameter profile as the XML profiles write it.

    Args:
        name: The parameter, argument or result name.
        code: The ``data_type_ref`` code, for example ``int`` or ``string[]``.
        description: The description, word for word from the XML profile.
        default_value: The default value, empty when the profile gives none.
    """
    return ParameterProfile(
        name=name,
        data_type_ref=RoISIdentifierType(code=code),
        default_value=default_value,
        description=description,
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

ROIS_COMMON_PROFILE = HRIComponentProfile(
    identifier=omg_identifier("RoISCommon"),
    name="rois_common",
    command_profiles=[
        CommandMessageProfile(name="start"),
        CommandMessageProfile(name="stop"),
        CommandMessageProfile(name="suspend"),
        CommandMessageProfile(name="resume"),
    ],
    query_profiles=[
        QueryMessageProfile(
            name="component_status",
            results=[parameter("status", "Component_Status")],
        ),
    ],
)
"""The RoIS_Common profile from RoISCommon.xml.

The status result has the type ``Component_Status``, the enumeration, so its value on
the wire is a name such as ``READY``.
"""
