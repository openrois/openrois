"""Per-component typed message models.

Each module in this sub-package defines typed Pydantic models for a specific
RoIS component's command, query, and event messages. These provide compile-time
safety and clear field documentation instead of using the generic
``Result(value=str)`` for event payloads.
"""

from openrois.interfaces.components.navigation import (
    NAVIGATION_URN,
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)
from openrois.interfaces.components.person_detection import (
    PERSON_DETECTION_URN,
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)
from openrois.interfaces.components.reaction import (
    REACTION_URN,
    ReactionGetParameterResult,
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionStatusResult,
)
from openrois.interfaces.components.system_information import (
    SYSTEM_INFORMATION_URN,
    SystemInformationEngineStatusResult,
    SystemInformationRobotPositionResult,
)

__all__ = [
    # PersonDetection
    "PERSON_DETECTION_URN",
    "PersonDetectedEvent",
    "PersonDetectionStatusResult",
    # Navigation
    "NAVIGATION_URN",
    "NavigationSetParameter",
    "NavigationSetParameterResult",
    "NavigationGetParameterResult",
    "NavigationStatusResult",
    "NavigationReachedTargetEvent",
    # Reaction
    "REACTION_URN",
    "ReactionSetParameter",
    "ReactionSetParameterResult",
    "ReactionGetParameterResult",
    "ReactionStatusResult",
    # SystemInformation
    "SYSTEM_INFORMATION_URN",
    "SystemInformationRobotPositionResult",
    "SystemInformationEngineStatusResult",
]
