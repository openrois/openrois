"""AudioStreaming and VideoStreaming component profiles.

Derived from:
  - OMG RoIS Framework 2.0, AudioStreaming.xml and VideoStreaming.xml
  - OMG RoIS Framework 2.0, RoIS_Audio_Streaming.idl and RoIS_Video_Streaming.idl

Component URNs:
  - urn:x-rois:def:component:OMG::AudioStreaming
  - urn:x-rois:def:component:OMG::VideoStreaming

Streaming has no interface of its own. A streaming component carries its messages on
the Command, Query and Event interfaces (spec 8.2.2.5, 8.4.18, 8.4.19): commands open,
close, suspend and resume a stream, the get_stream_status query reads one, and the
notify_stream_status event reports its changes. The query and the event take the
stream_id as an argument, which a client passes in the condition, for example
``stream_id = 'audio-1'``.

The two profiles are the same apart from their names. VideoStreaming.xml describes its
parameters with the words of AudioStreaming.xml, "the audio stream", and the constant
keeps them word for word.

This module is a local copy until the profile generator writes the constants from the
XML files.
"""

from __future__ import annotations

from openrois.interfaces.components.rois_common import (
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    omg_identifier,
    parameter,
)
from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    QueryMessageProfile,
)

# ---------------------------------------------------------------------------
# Component identifiers
# ---------------------------------------------------------------------------

AUDIO_STREAMING_URN = "urn:x-rois:def:component:OMG::AudioStreaming"
"""Canonical URN for the AudioStreaming component profile."""

VIDEO_STREAMING_URN = "urn:x-rois:def:component:OMG::VideoStreaming"
"""Canonical URN for the VideoStreaming component profile."""


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def _streaming_profile(code: str, name: str) -> HRIComponentProfile:
    """The profile both streaming XML files describe, under one type and name."""
    stream_id = parameter("stream_id", "String", "the ID of the stream")
    return HRIComponentProfile(
        identifier=omg_identifier(code),
        name=name,
        function=ComponentFunction.FUNCTION,
        sub_component_profiles=[ROIS_COMMON_URN],
        command_profiles=[
            *ROIS_COMMON_PROFILE.command_profiles,
            CommandMessageProfile(name="connect_stream", results=[stream_id]),
            CommandMessageProfile(name="disconnect_stream", arguments=[stream_id]),
            CommandMessageProfile(name="suspend_stream", arguments=[stream_id]),
            CommandMessageProfile(name="resume_stream", arguments=[stream_id]),
        ],
        query_profiles=[
            *ROIS_COMMON_PROFILE.query_profiles,
            QueryMessageProfile(
                name="get_stream_status",
                arguments=[stream_id],
                results=[parameter("status", "Stream_Status")],
            ),
        ],
        event_profiles=[
            EventMessageProfile(
                name="notify_stream_status",
                arguments=[stream_id],
                results=[
                    parameter("timestamp", "DateTime", "time when status changed"),
                    parameter("status", "Stream_Status", "status of the stream"),
                ],
            ),
        ],
        parameter_profiles=[
            parameter(
                "encoding_parameters", "String", "parameters to encode the audio stream"
            ),
            parameter(
                "transport_parameters", "String", "parameters to transport the audio stream"
            ),
            parameter(
                "available_encodings", "String", "available parameters to encode the audio stream"
            ).model_copy(update={"read_only": True}),
            parameter(
                "available_transports",
                "String",
                "available parameters to transport the audio stream",
            ).model_copy(update={"read_only": True}),
        ],
    )


AUDIO_STREAMING_PROFILE = _streaming_profile("AudioStreaming", "audio_streaming")
"""The full AudioStreaming profile.

AudioStreaming.xml with the RoIS_Common messages it includes, and the RoSO function
``function``. The spec lists ``available_encodings`` and ``available_transports`` only
under get_parameter, so they are read-only.
"""

VIDEO_STREAMING_PROFILE = _streaming_profile("VideoStreaming", "video_streaming")
"""The full VideoStreaming profile, the same messages as AudioStreaming."""
