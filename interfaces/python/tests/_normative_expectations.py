"""What the 18 normative XML component profiles must contain.

Each entry restates one OMG RoIS Framework 2.0 XML profile: its identifier, gml:name,
sub-profiles, every message (kind, name, arguments, results with their type codes) and
every parameter (name, type code, default_value). The source is the validation table of
the first-release plan (rows 1 to 35) and Tables 8.37 to 8.57 of the 2.0-beta2 PDF.
Where the XML and the PDF differ, the entry follows the XML and ``rows`` names the
validation row that records the difference.

Nothing here is copied from the files: the cross-check in ``test_xml_crosscheck.py``
parses the files and compares them with these entries, so an edited or replaced file
fails the suite.

A default is the ``default_value`` attribute as written: ``None`` when the attribute is
absent, ``""`` when it is present and empty (row 22).
"""

from __future__ import annotations

from dataclasses import dataclass

COMMAND = "Command"
QUERY = "Query"
EVENT = "Event"

ROIS_COMMON_REF = "urn:x-rois:def:Component:OMG::RoISCommon"

# Row 33. The type codes the 18 profiles use, and no other: twelve spellings, ten codes
# once case is ignored. The PDF types every field by
# its UML type (UnlimitedNatural, List<RoIS_Identifier>, ...); the files use these codes.
TYPE_CODES = frozenset(
    {
        "string",
        "String",
        "int",
        "bool",
        "string[]",
        "String[]",
        "int[]",
        "RoISIdentifier",
        "RoISIdentifier[]",
        "DateTime",
        "Component_Status",
        "Stream_Status",
    }
)


@dataclass(frozen=True)
class Field:
    """An argument or a result of a message: name and type code."""

    name: str
    code: str


@dataclass(frozen=True)
class Message:
    """A MessageProfile, by kind (the xsi:type without MessageProfileType)."""

    kind: str
    name: str
    arguments: tuple[Field, ...] = ()
    results: tuple[Field, ...] = ()
    rows: tuple[int, ...] = ()


@dataclass(frozen=True)
class Parameter:
    """A ParameterProfile: name, type code and default_value as written."""

    name: str
    code: str
    default: str | None = None
    rows: tuple[int, ...] = ()


@dataclass(frozen=True)
class Profile:
    """One XML component profile file."""

    file: str
    identifier: str
    name: str
    sub_profiles: tuple[str, ...] = (ROIS_COMMON_REF,)
    messages: tuple[Message, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    rows: tuple[int, ...] = ()


def _urn(code: str) -> str:
    return f"urn:x-rois:def:component:OMG::{code}"


_TIMESTAMP = Field("timestamp", "DateTime")
_STREAM_ID = Field("stream_id", "String")


def _detection(code: str, name: str, event: str) -> Profile:
    """Tables 8.42, 8.45, 8.47: one event with number and timestamp (row 21)."""
    return Profile(
        file=f"{code}.xml",
        identifier=_urn(code),
        name=name,
        messages=(
            Message(EVENT, event, results=(Field("number", "int"), _TIMESTAMP), rows=(21,)),
        ),
        rows=(21,),
    )


def _localization(code: str, name: str, event: str, ref: str) -> Profile:
    """Tables 8.43, 8.46, 8.48: two int parameters with an empty default (row 22)."""
    return Profile(
        file=f"{code}.xml",
        identifier=_urn(code),
        name=name,
        messages=(
            Message(
                EVENT,
                event,
                results=(
                    Field(ref, "RoISIdentifier[]"),
                    _TIMESTAMP,
                    Field("position_data", "String[]"),
                ),
                rows=(22,),
            ),
        ),
        parameters=(
            Parameter("detection_threshold", "int", "", rows=(22,)),
            Parameter("minimum_interval", "int", "", rows=(22,)),
        ),
        rows=(22,),
    )


def _streaming(code: str, name: str, rows: tuple[int, ...]) -> Profile:
    """Tables 8.56 and 8.57. Rows 8 to 10 (and 29 for video)."""
    return Profile(
        file=f"{code}.xml",
        identifier=_urn(code),
        name=name,
        messages=(
            Message(COMMAND, "connect_stream", results=(_STREAM_ID,)),
            Message(COMMAND, "disconnect_stream", arguments=(_STREAM_ID,)),
            Message(COMMAND, "suspend_stream", arguments=(_STREAM_ID,)),
            Message(COMMAND, "resume_stream", arguments=(_STREAM_ID,)),
            # Row 8: Table 8.6 calls it query_stream_status; Table 8.56 and the file agree.
            Message(
                QUERY,
                "get_stream_status",
                arguments=(_STREAM_ID,),
                results=(Field("status", "Stream_Status"),),
                rows=(8, 9),
            ),
            # Row 9: the PDF lists all three as arguments; the file keeps stream_id as
            # the only argument and returns timestamp and status.
            Message(
                EVENT,
                "notify_stream_status",
                arguments=(_STREAM_ID,),
                results=(_TIMESTAMP, Field("status", "Stream_Status")),
                rows=(9,),
            ),
        ),
        parameters=(
            Parameter("encoding_parameters", "String", ""),
            Parameter("transport_parameters", "String", ""),
            # Row 10: listed only under get_parameter in the PDF; the files make them
            # parameters, so they are settable in form.
            Parameter("available_encodings", "String", "", rows=(10,)),
            Parameter("available_transports", "String", "", rows=(10,)),
        ),
        rows=rows,
    )


PROFILES: tuple[Profile, ...] = (
    # Table 8.37. Row 14: identical. The only file whose URN spells "Component".
    Profile(
        file="RoISCommon.xml",
        identifier=ROIS_COMMON_REF,
        name="rois_common",
        sub_profiles=(),
        messages=(
            Message(COMMAND, "start"),
            Message(COMMAND, "stop"),
            Message(COMMAND, "suspend"),
            Message(COMMAND, "resume"),
            Message(QUERY, "component_status", results=(Field("status", "Component_Status"),)),
        ),
        rows=(14,),
    ),
    # Table 8.41. Row 20: no RoIS_Common, operable_time a single DateTime.
    Profile(
        file="SystemInformation.xml",
        identifier=_urn("SystemInformation"),
        name="system_info",
        sub_profiles=(),
        messages=(
            Message(
                QUERY,
                "robot_position",
                results=(
                    Field("position_data", "String[]"),
                    Field("robot_ref", "RoISIdentifier[]"),
                    _TIMESTAMP,
                ),
            ),
            Message(
                QUERY,
                "engine_status",
                results=(Field("operable_time", "DateTime"), Field("status", "Component_Status")),
                rows=(20,),
            ),
        ),
        rows=(20,),
    ),
    _detection("PersonDetection", "person_detecter", "person_detected"),
    _localization("PersonLocalization", "person_localizer", "person_localized", "person_ref"),
    # Table 8.44. Row 23: identical.
    Profile(
        file="PersonIdentification.xml",
        identifier=_urn("PersonIdentification"),
        name="person_identifier",
        messages=(
            Message(
                EVENT,
                "person_identified",
                results=(Field("person_ref", "RoISIdentifier[]"), _TIMESTAMP),
            ),
        ),
        rows=(23,),
    ),
    _detection("FaceDetection", "face_detecter", "face_detected"),
    _localization("FaceLocalization", "face_localizer", "face_localized", "face_ref"),
    _detection("SoundDetection", "sound_detecter", "sound_detected"),
    _localization("SoundLocalization", "sound_localizer", "sound_localized", "sound_ref"),
    # Table 8.49. Row 24: grammar spelled correctly, recognizable_languages a query,
    # languages defaults to "jp".
    Profile(
        file="SpeechRecognition.xml",
        identifier=_urn("SpeechRecognition"),
        name="speech_recognizer",
        messages=(
            Message(EVENT, "speech_input_started", results=(_TIMESTAMP,)),
            Message(EVENT, "speech_input_finished", results=(_TIMESTAMP,)),
            Message(
                EVENT,
                "speech_recognized",
                results=(Field("recognized_text", "string[]"), _TIMESTAMP),
            ),
            Message(
                QUERY,
                "recognizable_languages",
                results=(Field("languages", "string[]"),),
                rows=(24,),
            ),
        ),
        parameters=(
            Parameter("rule", "string", "default"),
            Parameter("languages", "string[]", "jp", rows=(24,)),
            Parameter("grammar", "string", "default", rows=(24,)),
        ),
        rows=(24,),
    ),
    # Table 8.50. Row 25: recognizable_gestures is a parameter, read-only by ruling.
    Profile(
        file="GestureRecognition.xml",
        identifier=_urn("GestureRecognition"),
        name="gesture_recognizer",
        messages=(
            Message(
                EVENT,
                "gesture_recognized",
                results=(Field("gesture_ref", "RoISIdentifier[]"), _TIMESTAMP),
            ),
        ),
        parameters=(Parameter("recognizable_gestures", "RoISIdentifier[]", "", rows=(25,)),),
        rows=(25,),
    ),
    # Table 8.51. Rows 11 and 12: two queries instead of get_parameter results,
    # character a string, the SSML parameter spelled ssml_text.
    Profile(
        file="SpeechSynthesis.xml",
        identifier=_urn("SpeechSynthesis"),
        name="speech_synthesizer",
        messages=(
            Message(
                QUERY,
                "synthesizable_languages",
                results=(Field("languages", "string[]"),),
                rows=(11,),
            ),
            Message(
                QUERY,
                "available_voices",
                results=(Field("characters", "string[]"),),
                rows=(11,),
            ),
        ),
        parameters=(
            Parameter("speech_text", "string"),
            Parameter("ssml_text", "string", rows=(12,)),
            Parameter("volume", "int", "50"),
            Parameter("language", "string", "en"),
            Parameter("character", "string", "default", rows=(11,)),
        ),
        rows=(11, 12),
    ),
    # Table 8.52. Row 26: available_reactions a query, a single reaction_ref.
    Profile(
        file="Reaction.xml",
        identifier=_urn("Reaction"),
        name="reaction",
        messages=(
            Message(
                QUERY,
                "available_reactions",
                results=(Field("available_reactions", "RoISIdentifier[]"),),
                rows=(26,),
            ),
        ),
        parameters=(Parameter("reaction_ref", "RoISIdentifier", rows=(26,)),),
        rows=(26,),
    ),
    # Table 8.53. Row 13: target_positions string[], time_limit int defaulting to 0,
    # and the reached_target event the PDF does not define.
    Profile(
        file="Navigation.xml",
        identifier=_urn("Navigation"),
        name="navigation",
        messages=(
            Message(
                EVENT,
                "reached_target",
                results=(Field("target", "string"), Field("is_final_target", "bool")),
                rows=(13,),
            ),
        ),
        parameters=(
            Parameter("target_positions", "string[]", rows=(13,)),
            Parameter("time_limit", "int", "0", rows=(13,)),
            Parameter("routing_policy", "string", "time"),
        ),
        rows=(13,),
    ),
    # Table 8.54. Row 27: identical, int types, no defaults.
    Profile(
        file="Follow.xml",
        identifier=_urn("Follow"),
        name="follower",
        parameters=(
            Parameter("target_object_ref", "RoISIdentifier"),
            Parameter("distance", "int"),
            Parameter("time_limit", "int"),
        ),
        rows=(27,),
    ),
    # Table 8.55. Row 28: identical, int[] and int.
    Profile(
        file="Move.xml",
        identifier=_urn("Move"),
        name="move",
        parameters=(
            Parameter("line", "int[]"),
            Parameter("curve", "int[]"),
            Parameter("time", "int"),
        ),
        rows=(28,),
    ),
    _streaming("AudioStreaming", "audio_streaming", rows=(8, 9, 10)),
    _streaming("VideoStreaming", "video_streaming", rows=(8, 9, 10, 29)),
)

PROFILE_FILES: tuple[str, ...] = tuple(p.file for p in PROFILES)

# Files whose root element does not parse with a strict XML parser, as they stand, and
# the defect. A corrected file flips the test that asserts the defect.
# FaceLocalization.xml declares xmlns:rois="http://www.omg.org/spec/RoIS/20240801 " with
# a trailing space, which libxml2 rejects as an invalid URI. Validation row 36.
STRICT_PARSE_DEFECTS: dict[str, tuple[bytes, bytes]] = {
    "FaceLocalization.xml": (
        b'xmlns:rois="http://www.omg.org/spec/RoIS/20240801 "',
        b'xmlns:rois="http://www.omg.org/spec/RoIS/20240801"',
    ),
}

# Python enums against the IDL enum bodies: (IDL file, IDL enum name).
IDL_ENUMS: dict[str, tuple[str, str]] = {
    "ReturnCode": ("RoIS_HRI.idl", "ReturnCode_t"),
    "ComponentStatus": ("RoIS_Common.idl", "Component_Status"),
    "StreamStatus": ("RoIS_Common.idl", "Stream_Status"),
    "CompletedStatus": ("RoIS_Service.idl", "Completed_Status"),
    "ErrorType": ("RoIS_Service.idl", "ErrorType"),
}

# Row 35 and Table 8.40: the RoSO function OWL.ttl assigns to each component type.
# OWL.ttl places the streaming types under RoboticServiceOntology/Function and the others
# under RoboticServiceFunctionOntology/Sensing or /Actuation. RoISCommon and
# SystemInformation have no class in the ontology.
ROSO_FUNCTIONS: dict[str, str | None] = {
    "RoISCommon": None,
    "SystemInformation": None,
    "PersonDetection": "sensing",
    "PersonLocalization": "sensing",
    "PersonIdentification": "sensing",
    "FaceDetection": "sensing",
    "FaceLocalization": "sensing",
    "SoundDetection": "sensing",
    "SoundLocalization": "sensing",
    "SpeechRecognition": "sensing",
    "GestureRecognition": "sensing",
    "SpeechSynthesis": "actuation",
    "Reaction": "actuation",
    "Navigation": "actuation",
    "Follow": "actuation",
    "Move": "actuation",
    "AudioStreaming": "function",
    "VideoStreaming": "function",
}
