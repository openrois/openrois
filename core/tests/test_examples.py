"""The shipped examples keep working: the mixed-paradigm demo runs end to end."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def test_mixed_paradigm_demo_completes_on_both_sides() -> None:
    demo = load("mixed_paradigm_demo", EXAMPLES / "mixed-paradigm" / "demo.py")
    outcome = await demo.run(0)
    assert sorted(outcome["speakers"]) == ["avatar_1/SpeechSynthesis", "robot_1/SpeechSynthesis"]
    assert set(outcome["positions"]) == {"avatar_1/SystemInformation", "robot_1/SystemInformation"}
    assert outcome["completions"] == {
        "avatar_1/SpeechSynthesis": "OK",
        "robot_1/SpeechSynthesis": "OK",
    }
