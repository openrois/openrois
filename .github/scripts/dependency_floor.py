#!/usr/bin/env python3
"""Print the lowest version a pyproject.toml allows for one of its dependencies.

A release tests the oldest version of a dependency that its consumers can get, which is the
floor its ``>=`` specifier declares. A dependency without such a floor exits non-zero, so a
release cannot test against a version it did not choose.

Usage:
    python3 .github/scripts/dependency_floor.py services/mcp/pyproject.toml openrois-sdk
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

#: A requirement: the name, optional extras, then the version specifiers.
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")


def normalized(name: str) -> str:
    """A distribution name as PyPI compares it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def floor(pyproject: Path, dependency: str) -> str:
    """Return the version after ``>=`` in the requirement of ``dependency``."""
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        sys.exit(f"::error::{pyproject}: {error}")
    for requirement in project.get("dependencies", []):
        match = REQUIREMENT.match(requirement.split(";")[0])
        if match is None or normalized(match.group(1)) != normalized(dependency):
            continue
        for specifier in match.group(2).split(","):
            specifier = specifier.strip()
            if specifier.startswith(">="):
                return specifier[2:].strip()
        sys.exit(f"::error::{pyproject}: {requirement} declares no >= floor")
    sys.exit(f"::error::{pyproject} does not depend on {dependency}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pyproject", type=Path, help="the pyproject.toml to read")
    parser.add_argument("dependency", help="the distribution name, such as openrois-sdk")
    args = parser.parse_args()
    print(floor(args.pyproject, args.dependency))


if __name__ == "__main__":
    main()
