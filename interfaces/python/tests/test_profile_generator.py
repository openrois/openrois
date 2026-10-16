"""Tests for tools/generate_profiles.py and the constants it writes (stream I, step 5).

The 18 profile constants of ``openrois.interfaces.components`` come from the OMG files:
the generator reads them with the XML codec and writes ``standard_profiles.py``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from openrois.interfaces import components
from openrois.interfaces.components import standard_profiles
from openrois.interfaces.profiles import ComponentFunction, HRIComponentProfile
from tests._normative import ENV_VAR, NORMATIVE_DIR, requires_normative

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR = _PACKAGE_ROOT / "tools" / "generate_profiles.py"


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_profiles", _GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STANDARD_NAMES = [
    "ROIS_COMMON",
    "AUDIO_STREAMING",
    "FACE_DETECTION",
    "FACE_LOCALIZATION",
    "FOLLOW",
    "GESTURE_RECOGNITION",
    "MOVE",
    "NAVIGATION",
    "PERSON_DETECTION",
    "PERSON_IDENTIFICATION",
    "PERSON_LOCALIZATION",
    "REACTION",
    "SOUND_DETECTION",
    "SOUND_LOCALIZATION",
    "SPEECH_RECOGNITION",
    "SPEECH_SYNTHESIS",
    "SYSTEM_INFORMATION",
    "VIDEO_STREAMING",
]


def test_eighteen_constants_are_exported() -> None:
    for name in STANDARD_NAMES:
        assert isinstance(getattr(components, f"{name}_PROFILE"), HRIComponentProfile)
        assert getattr(components, f"{name}_URN").startswith("urn:x-rois:def:")


def test_profiles_document_lists_all_eighteen() -> None:
    names = [p["name"] for p in components.profiles_document()["profiles"]]  # type: ignore[index]
    assert sorted(names) == sorted(f"{n}_PROFILE" for n in STANDARD_NAMES)


def test_read_only_parameters() -> None:
    """Rows 10 and 25: parameters the spec lists only under get_parameter."""
    read_only = {
        (profile.name, p.name)
        for profile in standard_profiles.STANDARD_PROFILES.values()
        for p in profile.parameter_profiles
        if p.read_only
    }
    assert read_only == {
        ("audio_streaming", "available_encodings"),
        ("audio_streaming", "available_transports"),
        ("video_streaming", "available_encodings"),
        ("video_streaming", "available_transports"),
        ("gesture_recognizer", "recognizable_gestures"),
    }


def test_streaming_is_function() -> None:
    assert components.AUDIO_STREAMING_PROFILE.function is ComponentFunction.FUNCTION
    assert components.VIDEO_STREAMING_PROFILE.function is ComponentFunction.FUNCTION


def test_registry_holds_the_standard_profiles() -> None:
    registry = standard_profiles.standard_registry()
    assert registry.get(components.ROIS_COMMON_URN) == components.ROIS_COMMON_PROFILE
    assert registry.get(components.NAVIGATION_URN) == components.NAVIGATION_PROFILE


def test_generator_needs_the_normative_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--check"],
        capture_output=True,
        text=True,
        env={"PATH": ""},
        cwd=_PACKAGE_ROOT,
    )
    assert result.returncode != 0
    assert ENV_VAR in result.stderr


@requires_normative
class TestGenerated:
    def test_constants_are_up_to_date(self) -> None:
        """The committed module is what the generator writes from the normative files."""
        generator = _generator()
        expected = generator.render(generator.build_profiles(NORMATIVE_DIR))
        assert standard_profiles.__file__ is not None
        assert Path(standard_profiles.__file__).read_text() == expected

    @pytest.mark.parametrize("name", STANDARD_NAMES)
    def test_constant_matches_the_files(self, name: str) -> None:
        built = _generator().build_profiles(NORMATIVE_DIR)
        urn, profile = built[name]
        assert getattr(components, f"{name}_URN") == urn
        assert getattr(components, f"{name}_PROFILE") == profile

    def test_check_mode_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_GENERATOR), "--check"],
            capture_output=True,
            text=True,
            env={ENV_VAR: str(NORMATIVE_DIR), "PATH": ""},
            cwd=_PACKAGE_ROOT,
        )
        assert result.returncode == 0, result.stderr
