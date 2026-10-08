"""SpeechSynthesis component profile.

Derived from:
  - OMG RoIS Framework 2.0, SpeechSynthesis.xml
  - OMG RoIS Framework 2.0, RoIS_Speech_Synthesis.idl

Component URN: urn:x-rois:def:component:OMG::SpeechSynthesis

The SpeechSynthesis component inherits from RoIS_Common:
  - Command: start(), stop(), suspend(), resume(), set_parameter()
  - Query: component_status(), get_parameter()
  - Event: (no component-specific events)

The SpeechSynthesis component speaks a text, given as plain text or as SSML, with a
volume, a language and a voice character. On a physical robot it plays synthesized
speech on a speaker. On a virtual avatar it voices the avatar. The engine behind the
voice, local or a cloud service, is the host's choice, and the
``synthesizable_languages`` and ``available_voices`` queries tell a client what it offers.
"""

from __future__ import annotations

from openrois.interfaces.components.rois_common import (
    ROIS_COMMON_PROFILE,
    ROIS_COMMON_URN,
    omg_identifier,
    parameter,
)
from openrois.interfaces.profiles import (
    ComponentFunction,
    HRIComponentProfile,
    QueryMessageProfile,
)

# ---------------------------------------------------------------------------
# Component identifier
# ---------------------------------------------------------------------------

SPEECH_SYNTHESIS_URN = "urn:x-rois:def:component:OMG::SpeechSynthesis"
"""Canonical URN for the SpeechSynthesis component profile."""


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

SPEECH_SYNTHESIS_PROFILE = HRIComponentProfile(
    identifier=omg_identifier("SpeechSynthesis"),
    name="speech_synthesizer",
    function=ComponentFunction.ACTUATION,
    sub_component_profiles=[ROIS_COMMON_URN],
    command_profiles=[*ROIS_COMMON_PROFILE.command_profiles],
    query_profiles=[
        *ROIS_COMMON_PROFILE.query_profiles,
        QueryMessageProfile(
            name="synthesizable_languages",
            results=[parameter("languages", "string[]", "list of available languages")],
        ),
        QueryMessageProfile(
            name="available_voices",
            results=[parameter("characters", "string[]", "list of available voice characters")],
        ),
    ],
    parameter_profiles=[
        parameter("speech_text", "string", "speech text in plain text"),
        parameter("ssml_text", "string", "speech text in SSML text"),
        parameter("volume", "int", "Volume", "50"),
        parameter("language", "string", "Language of the speech", "en"),
        parameter("character", "string", "character of the voice", "default"),
    ],
)
"""The full SpeechSynthesis profile.

SpeechSynthesis.xml with the RoIS_Common messages it includes, and the RoSO function
``actuation``. The profile follows the XML: ``character`` is a ``string``, and the
languages and voices are the ``synthesizable_languages`` and ``available_voices``
queries (docs/rois-reference.md, section 16, item 9).
"""
