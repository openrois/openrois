"""Generate the 18 standard profile constants from the OMG RoIS normative files.

Developer script. It reads the XML profiles and OWL.ttl from the directory that
OPENROIS_NORMATIVE_DIR names, with the XML codec of ``openrois.interfaces``, and writes
``src/openrois/interfaces/components/standard_profiles.py``. The normative files are not
redistributed with OpenRoIS, so the generated module is committed.

Each constant is the full profile of its type:

- the XML profile, read with the RoIS_Common profile in the registry, so the messages
  of RoIS_Common come first;
- the RoSO function the ontology OWL.ttl assigns to the type (an OpenRoIS extension);
- ``read_only`` on the parameters the specification lists only under get_parameter
  (validation rows 10 and 25, an OpenRoIS extension).

Usage:

    OPENROIS_NORMATIVE_DIR=/path/to/machine-readable python tools/generate_profiles.py
    OPENROIS_NORMATIVE_DIR=/path/to/machine-readable python tools/generate_profiles.py --check

``--check`` writes nothing and exits with status 1 when the module is out of date.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from openrois.interfaces.profiles import ComponentFunction, HRIComponentProfile
from openrois.interfaces.xmlcodec import ProfileRegistry, read_component_profile

ENV_VAR = "OPENROIS_NORMATIVE_DIR"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TARGET = PACKAGE_ROOT / "src" / "openrois" / "interfaces" / "components" / "standard_profiles.py"

ROIS_COMMON_FILE = "RoISCommon.xml"

# Not a component profile: the Enterprise Architect export of the UML model (row 35).
NOT_PROFILES = frozenset({"Model.xml"})

# Parameters the specification lists only under get_parameter (rows 10 and 25).
READ_ONLY: dict[str, frozenset[str]] = {
    "AudioStreaming": frozenset({"available_encodings", "available_transports"}),
    "VideoStreaming": frozenset({"available_encodings", "available_transports"}),
    "GestureRecognition": frozenset({"recognizable_gestures"}),
}

_ONTOLOGY_COMPONENT = (
    "https://www.omg.org/spec/RoIS/Ontology/RoboticInteractionServiceComponentOntology/"
)
# Sensing and Actuation sit in RoboticServiceFunctionOntology, Function in
# RoboticServiceOntology.
_ONTOLOGY_PARENT = re.compile(
    r"rdfs:subClassOf <https://www\.omg\.org/spec/RoSO/\w+/(Sensing|Actuation|Function)>"
)
_IDENTIFIER = re.compile(r"<gml:identifier[^>]*>\s*([^<]+?)\s*</gml:identifier>")

LINE_LENGTH = 100
INDENT = "    "


# ---------------------------------------------------------------------------
# Reading the normative files
# ---------------------------------------------------------------------------


def constant_prefix(code: str) -> str:
    """The constant name prefix of a component type: ``SpeechSynthesis`` → ``SPEECH_SYNTHESIS``."""
    if code == "RoISCommon":
        return "ROIS_COMMON"
    return re.sub(r"(?<!^)(?=[A-Z])", "_", code).upper()


def ontology_function(owl: str, code: str) -> ComponentFunction | None:
    """The RoSO class OWL.ttl assigns to a component type, or None."""
    block = re.search(
        rf"<{re.escape(_ONTOLOGY_COMPONENT + code)}>(.*?)\s\.\s*$",
        owl,
        re.DOTALL | re.MULTILINE,
    )
    if block is None:
        return None
    parent = _ONTOLOGY_PARENT.search(block.group(1))
    return ComponentFunction(parent.group(1).lower()) if parent else None


def _urn(path: Path) -> str:
    """The gml:identifier text of a profile file, exactly as the file writes it."""
    match = _IDENTIFIER.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"{path.name} has no gml:identifier")
    return match.group(1)


def _finish(profile: HRIComponentProfile, owl: str) -> HRIComponentProfile:
    read_only = READ_ONLY.get(profile.identifier.code, frozenset())
    return profile.model_copy(
        update={
            "function": ontology_function(owl, profile.identifier.code),
            "parameter_profiles": [
                p.model_copy(update={"read_only": True}) if p.name in read_only else p
                for p in profile.parameter_profiles
            ],
        }
    )


def build_profiles(normative_dir: Path) -> dict[str, tuple[str, HRIComponentProfile]]:
    """The URN and full profile of every standard type, by constant prefix.

    RoIS_Common comes first, the other types follow in the order of their code.
    """
    owl = (normative_dir / "OWL.ttl").read_text(encoding="utf-8")
    registry = ProfileRegistry()
    common_path = normative_dir / ROIS_COMMON_FILE
    common = _finish(registry.load(common_path), owl)
    registry.add(common)
    built = {constant_prefix(common.identifier.code): (_urn(common_path), common)}
    others = []
    for path in sorted(normative_dir.glob("*.xml")):
        if path.name in NOT_PROFILES or path.name == ROIS_COMMON_FILE:
            continue
        others.append((path, _finish(read_component_profile(path, registry=registry), owl)))
    for path, profile in sorted(others, key=lambda item: item[1].identifier.code):
        built[constant_prefix(profile.identifier.code)] = (_urn(path), profile)
    return built


# ---------------------------------------------------------------------------
# Writing the module
# ---------------------------------------------------------------------------

_HEADER = '''"""The profile constants of the 18 standard RoIS component types.

Generated by tools/generate_profiles.py from the OMG RoIS Framework 2.0 normative files,
the XML profiles and OWL.ttl. Do not edit this module by hand: run the generator.

Each constant is the full profile of its type: the XML profile with the messages of the
RoIS_Common profile it includes listed first, the RoSO function that OWL.ttl assigns to
the type, and ``read_only`` on the parameters the specification lists only under
get_parameter. A component declares the constant of its type and implements a part of
it.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from openrois.interfaces.profiles import (
    CommandMessageProfile,
    ComponentFunction,
    EventMessageProfile,
    HRIComponentProfile,
    ParameterProfile,
    QueryMessageProfile,
    RoISIdentifierType,
)

if TYPE_CHECKING:
    from openrois.interfaces.xmlcodec import ProfileRegistry
'''

_FOOTER = '''

def standard_registry() -> ProfileRegistry:
    """A registry that holds the 18 standard profiles, for resolving sub-profiles."""
    from openrois.interfaces.xmlcodec import ProfileRegistry

    return ProfileRegistry(STANDARD_PROFILES.values())
'''


def _literal(value: object) -> str:
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def _fields(model: BaseModel) -> list[tuple[str, object]]:
    fields = []
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        if field.is_required() or value != field.get_default(call_default_factory=True):
            fields.append((name, value))
    return fields


def _one_line(value: object) -> str:
    if isinstance(value, BaseModel):
        args = ", ".join(f"{name}={_one_line(v)}" for name, v in _fields(value))
        return f"{type(value).__name__}({args})"
    if isinstance(value, list):
        return "[" + ", ".join(_one_line(v) for v in value) + "]"
    return _literal(value)


def _split_string(text: str, indent: str) -> str:
    """A long string as parenthesized implicit concatenation."""
    width = LINE_LENGTH - len(indent) - len(INDENT) - 3
    words = re.split(r"(?<= )", text)
    parts: list[str] = []
    current = ""
    for word in words:
        if current and len(json.dumps(current + word, ensure_ascii=False)) > width:
            parts.append(current)
            current = ""
        current += word
    parts.append(current)
    inner = "".join(
        f"{indent}{INDENT}{json.dumps(p, ensure_ascii=False)}\n" for p in parts
    )
    return f"(\n{inner}{indent})"


def _emit(value: object, indent: str, used: int) -> str:
    """Python source for a value whose first line already holds ``used`` characters."""
    one_line = _one_line(value)
    if used + len(one_line) + 1 <= LINE_LENGTH:
        return one_line
    inner = indent + INDENT
    if isinstance(value, BaseModel):
        lines = []
        for name, v in _fields(value):
            prefix = f"{inner}{name}="
            lines.append(f"{prefix}{_emit(v, inner, len(prefix))},\n")
        return f"{type(value).__name__}(\n{''.join(lines)}{indent})"
    if isinstance(value, list):
        lines = [f"{inner}{_emit(v, inner, len(inner))},\n" for v in value]
        return f"[\n{''.join(lines)}{indent}]"
    if isinstance(value, str):
        return _split_string(value, indent)
    return one_line


def render(profiles: dict[str, tuple[str, HRIComponentProfile]]) -> str:
    """The source of ``standard_profiles.py``."""
    blocks = [_HEADER]
    for prefix, (urn, profile) in profiles.items():
        urn_line = f"{prefix}_URN = {_literal(urn)}"
        doc = f'"""URN of the {profile.identifier.code} profile, its gml:identifier."""'
        assignment = f"{prefix}_PROFILE = "
        blocks.append(
            f"\n{urn_line}\n{doc}\n\n{assignment}{_emit(profile, '', len(assignment))}\n"
        )
    entries = "".join(f'        "{p}_PROFILE": {p}_PROFILE,\n' for p in profiles)
    blocks.append(
        "\nSTANDARD_PROFILES: Mapping[str, HRIComponentProfile] = MappingProxyType(\n"
        f"    {{\n{entries}    }}\n)\n"
        '"""The standard profiles by constant name, RoIS_Common first."""\n'
    )
    blocks.append(_FOOTER)
    return "".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 when the module is out of date"
    )
    args = parser.parse_args(argv)
    configured = os.environ.get(ENV_VAR)
    if not configured or not Path(configured).expanduser().is_dir():
        print(
            f"{ENV_VAR} must name the directory of the OMG RoIS machine-readable files",
            file=sys.stderr,
        )
        return 2
    profiles = build_profiles(Path(configured).expanduser())
    source = render(profiles)
    if args.check:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != source:
            print(f"{TARGET} is out of date: run tools/generate_profiles.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(source, encoding="utf-8")
    print(f"Wrote {len(profiles)} profiles to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
