"""A stand-in for the engine that hosts a component in these tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from openrois.interfaces.hri import Parameter, Result
from openrois.interfaces.profiles import HRIComponentProfile


@dataclass
class RecordingBinding:
    """An EngineBinding that keeps parameters in a list and records every event."""

    ref: str = "robot/navigation"
    stored: list[Parameter] = field(default_factory=list)
    events: list[tuple[str, list[Result]]] = field(default_factory=list)

    @classmethod
    def with_defaults(
        cls, profile: HRIComponentProfile, ref: str = "robot/navigation"
    ) -> RecordingBinding:
        """A binding whose parameters hold the defaults of a profile, as an engine starts."""
        stored = [
            Parameter(name=p.name, data_type_ref=p.data_type_ref.code, value=p.default_value)
            for p in profile.parameter_profiles
        ]
        return cls(ref=ref, stored=stored)

    def parameters(self) -> Sequence[Parameter]:
        return self.stored

    def emit(self, event_type: str, results: Sequence[Result]) -> None:
        self.events.append((event_type, list(results)))
