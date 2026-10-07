"""Per-component profiles and typed message models.

Each module in this sub-package holds one RoIS component type: the full profile of
the type as a constant, and typed Pydantic models for its command, query and event
messages. The models provide compile-time safety and clear field documentation
instead of the generic ``Result(value=str)`` for event payloads.

A profile constant is the XML profile of the type with the RoIS_Common messages it
includes, and the RoSO function from the ontology. A component declares the constant
of its type and implements a part of it, and the engine serves the part it implements.
``profiles_document()`` writes the constants to ``schema/profiles.json``, which the
TypeScript generator reads.
"""

from collections.abc import Mapping
from types import MappingProxyType

from openrois.interfaces.components.navigation import (
    NAVIGATION_PROFILE,
    NAVIGATION_URN,
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)
from openrois.interfaces.components.person_detection import (
    PERSON_DETECTION_PROFILE,
    PERSON_DETECTION_URN,
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)
from openrois.interfaces.components.reaction import (
    REACTION_PROFILE,
    REACTION_URN,
    ReactionGetParameterResult,
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionStatusResult,
)
from openrois.interfaces.components.rois_common import (
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
)
from openrois.interfaces.components.system_information import (
    SYSTEM_INFORMATION_PROFILE,
    SYSTEM_INFORMATION_URN,
    SystemInformationEngineStatusResult,
    SystemInformationRobotPositionResult,
)
from openrois.interfaces.profiles import HRIComponentProfile

# The profile constants by name, in the order profiles.json lists them.
_PROFILES: Mapping[str, HRIComponentProfile] = MappingProxyType(
    {
        "ROIS_COMMON_PROFILE": ROIS_COMMON_PROFILE,
        "NAVIGATION_PROFILE": NAVIGATION_PROFILE,
        "PERSON_DETECTION_PROFILE": PERSON_DETECTION_PROFILE,
        "REACTION_PROFILE": REACTION_PROFILE,
        "SYSTEM_INFORMATION_PROFILE": SYSTEM_INFORMATION_PROFILE,
    }
)


def profiles_document() -> dict[str, object]:
    """Return the profile constants as the language-neutral document ``profiles.json``.

    The TypeScript generator reads this document and emits each profile as a constant
    with the same name, so every language serves the same profiles.
    """
    return {
        "profiles": [
            {"name": name, "profile": profile.model_dump(mode="json")}
            for name, profile in _PROFILES.items()
        ],
    }


__all__ = [
    "profiles_document",
    # RoIS_Common
    "ROIS_COMMON_URN",
    "ROIS_COMMON_PROFILE",
    # PersonDetection
    "PERSON_DETECTION_URN",
    "PERSON_DETECTION_PROFILE",
    "PersonDetectedEvent",
    "PersonDetectionStatusResult",
    # Navigation
    "NAVIGATION_URN",
    "NAVIGATION_PROFILE",
    "NavigationSetParameter",
    "NavigationSetParameterResult",
    "NavigationGetParameterResult",
    "NavigationStatusResult",
    "NavigationReachedTargetEvent",
    # Reaction
    "REACTION_URN",
    "REACTION_PROFILE",
    "ReactionSetParameter",
    "ReactionSetParameterResult",
    "ReactionGetParameterResult",
    "ReactionStatusResult",
    # SystemInformation
    "SYSTEM_INFORMATION_URN",
    "SYSTEM_INFORMATION_PROFILE",
    "SystemInformationRobotPositionResult",
    "SystemInformationEngineStatusResult",
]
