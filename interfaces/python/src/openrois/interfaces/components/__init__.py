"""Per-component profiles and typed message models.

``standard_profiles`` holds the full profile of each of the 18 standard RoIS component
types as a constant, generated from the OMG normative files by
``tools/generate_profiles.py``: the XML profile of the type with the RoIS_Common messages
it includes, the RoSO function from the ontology, and the read-only parameters. A
component declares the constant of its type and implements a part of it, and the engine
serves the part it implements. ``profiles_document()`` writes the constants to
``schema/profiles.json``, which the TypeScript generator reads.

The other modules hold typed Pydantic models for the command, query and event messages
of some types, which give clear field documentation instead of the generic
``Result(value=str)`` for event payloads.
"""

from openrois.interfaces.components.navigation import (
    NavigationGetParameterResult,
    NavigationReachedTargetEvent,
    NavigationSetParameter,
    NavigationSetParameterResult,
    NavigationStatusResult,
)
from openrois.interfaces.components.person_detection import (
    PersonDetectedEvent,
    PersonDetectionStatusResult,
)
from openrois.interfaces.components.reaction import (
    ReactionGetParameterResult,
    ReactionSetParameter,
    ReactionSetParameterResult,
    ReactionStatusResult,
)
from openrois.interfaces.components.standard_profiles import (
    AUDIO_STREAMING_PROFILE,
    AUDIO_STREAMING_URN,
    FACE_DETECTION_PROFILE,
    FACE_DETECTION_URN,
    FACE_LOCALIZATION_PROFILE,
    FACE_LOCALIZATION_URN,
    FOLLOW_PROFILE,
    FOLLOW_URN,
    GESTURE_RECOGNITION_PROFILE,
    GESTURE_RECOGNITION_URN,
    MOVE_PROFILE,
    MOVE_URN,
    NAVIGATION_PROFILE,
    NAVIGATION_URN,
    PERSON_DETECTION_PROFILE,
    PERSON_DETECTION_URN,
    PERSON_IDENTIFICATION_PROFILE,
    PERSON_IDENTIFICATION_URN,
    PERSON_LOCALIZATION_PROFILE,
    PERSON_LOCALIZATION_URN,
    REACTION_PROFILE,
    REACTION_URN,
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    SOUND_DETECTION_PROFILE,
    SOUND_DETECTION_URN,
    SOUND_LOCALIZATION_PROFILE,
    SOUND_LOCALIZATION_URN,
    SPEECH_RECOGNITION_PROFILE,
    SPEECH_RECOGNITION_URN,
    SPEECH_SYNTHESIS_PROFILE,
    SPEECH_SYNTHESIS_URN,
    STANDARD_PROFILES,
    SYSTEM_INFORMATION_PROFILE,
    SYSTEM_INFORMATION_URN,
    VIDEO_STREAMING_PROFILE,
    VIDEO_STREAMING_URN,
    standard_registry,
)
from openrois.interfaces.components.system_information import (
    SystemInformationEngineStatusResult,
    SystemInformationRobotPositionResult,
)


def profiles_document() -> dict[str, object]:
    """Return the profile constants as the language-neutral document ``profiles.json``.

    The TypeScript generator reads this document and emits each profile as a constant
    with the same name, so every language serves the same profiles.
    """
    return {
        "profiles": [
            {"name": name, "profile": profile.model_dump(mode="json")}
            for name, profile in STANDARD_PROFILES.items()
        ],
    }


__all__ = [
    "profiles_document",
    "STANDARD_PROFILES",
    "standard_registry",
    "ROIS_COMMON_URN",
    "ROIS_COMMON_PROFILE",
    "AUDIO_STREAMING_URN",
    "AUDIO_STREAMING_PROFILE",
    "FACE_DETECTION_URN",
    "FACE_DETECTION_PROFILE",
    "FACE_LOCALIZATION_URN",
    "FACE_LOCALIZATION_PROFILE",
    "FOLLOW_URN",
    "FOLLOW_PROFILE",
    "GESTURE_RECOGNITION_URN",
    "GESTURE_RECOGNITION_PROFILE",
    "MOVE_URN",
    "MOVE_PROFILE",
    "NAVIGATION_URN",
    "NAVIGATION_PROFILE",
    "PERSON_DETECTION_URN",
    "PERSON_DETECTION_PROFILE",
    "PERSON_IDENTIFICATION_URN",
    "PERSON_IDENTIFICATION_PROFILE",
    "PERSON_LOCALIZATION_URN",
    "PERSON_LOCALIZATION_PROFILE",
    "REACTION_URN",
    "REACTION_PROFILE",
    "SOUND_DETECTION_URN",
    "SOUND_DETECTION_PROFILE",
    "SOUND_LOCALIZATION_URN",
    "SOUND_LOCALIZATION_PROFILE",
    "SPEECH_RECOGNITION_URN",
    "SPEECH_RECOGNITION_PROFILE",
    "SPEECH_SYNTHESIS_URN",
    "SPEECH_SYNTHESIS_PROFILE",
    "SYSTEM_INFORMATION_URN",
    "SYSTEM_INFORMATION_PROFILE",
    "VIDEO_STREAMING_URN",
    "VIDEO_STREAMING_PROFILE",
    # Typed message models
    "PersonDetectedEvent",
    "PersonDetectionStatusResult",
    "NavigationSetParameter",
    "NavigationSetParameterResult",
    "NavigationGetParameterResult",
    "NavigationStatusResult",
    "NavigationReachedTargetEvent",
    "ReactionSetParameter",
    "ReactionSetParameterResult",
    "ReactionGetParameterResult",
    "ReactionStatusResult",
    "SystemInformationRobotPositionResult",
    "SystemInformationEngineStatusResult",
]
