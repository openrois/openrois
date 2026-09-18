#!/usr/bin/env python3
"""Fail when the packages of the monorepo do not share one version.

Python packages use PEP 440 pre-release spelling (0.1.0a3), npm and NuGet
packages use SemVer (0.1.0-alpha.3), and CITATION.cff uses the SemVer form.
The script normalizes both spellings and compares.

Usage: python scripts/check_versions.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PYPROJECTS = [
    "interfaces/python/pyproject.toml",
    "core/pyproject.toml",
    "components/core/pyproject.toml",
    "components/common/pyproject.toml",
    "components/kachaka/pyproject.toml",
]
PACKAGE_JSONS = [
    "interfaces/typescript/package.json",
    "sdk/typescript/package.json",
    "sdk/csharp/package.json",
    "examples/mock-engine/package.json",
    "examples/hri-client/package.json",
    "apps/hub/package.json",
]
CSPROJS = ["interfaces/csharp/src/OpenRoIS.Interfaces/OpenRoIS.Interfaces.csproj"]
CFF = "CITATION.cff"


def normalize(version: str) -> str:
    """Map 0.1.0a3 and 0.1.0-alpha.3 to the same key."""
    m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-?(alpha|beta|rc|a|b)\.?(\d+))?", version.strip())
    if not m:
        return version.strip()
    base, tag, n = m.groups()
    if not tag:
        return base
    tag = {"a": "alpha", "b": "beta"}.get(tag, tag)
    return f"{base}-{tag}.{n}"


def collect() -> dict[str, str]:
    found: dict[str, str] = {}
    for rel in PYPROJECTS:
        text = (ROOT / rel).read_text()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        found[rel] = m.group(1) if m else "?"
    for rel in PACKAGE_JSONS:
        found[rel] = str(json.loads((ROOT / rel).read_text()).get("version", "?"))
    for rel in CSPROJS:
        m = re.search(r"<Version>([^<]+)</Version>", (ROOT / rel).read_text())
        found[rel] = m.group(1) if m else "?"
    m = re.search(r"^version:\s*(\S+)", (ROOT / CFF).read_text(), re.M)
    found[CFF] = m.group(1) if m else "?"
    return found


def main() -> int:
    found = collect()
    keys = {normalize(v) for v in found.values()}
    width = max(len(k) for k in found)
    for rel, version in found.items():
        print(f"{rel:<{width}}  {version}")
    if len(keys) != 1:
        print(f"\nVersion drift: {sorted(keys)}", file=sys.stderr)
        return 1
    print(f"\nAll packages at {keys.pop()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
