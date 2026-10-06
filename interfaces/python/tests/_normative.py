"""Locate the OMG RoIS normative machine-readable files for the cross-check tests.

The repository does not redistribute these files. They carry OMG's copyright and
licence, and the project cannot edit them. Download the OMG RoIS Framework 2.0
machine-readable files from https://www.omg.org/spec/RoIS/2.0 and point
``OPENROIS_NORMATIVE_DIR`` at the directory that holds ``XML-Profiles.xsd`` and the
component XML profiles. Tests that need the files are skipped when they are not found.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ENV_VAR = "OPENROIS_NORMATIVE_DIR"

# tests/_normative.py  →  tests/  →  python/  →  interfaces/  →  repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]

# An untracked local copy at the repository root also works, so maintainers who keep
# the files there need no environment variable.
_DEFAULT_DIR = _REPO_ROOT / "normative" / "machine-readable"


def _resolve() -> Path:
    configured = os.environ.get(ENV_VAR)
    return Path(configured).expanduser() if configured else _DEFAULT_DIR


NORMATIVE_DIR = _resolve()

requires_normative = pytest.mark.skipif(
    not NORMATIVE_DIR.is_dir(),
    reason=(
        f"RoIS normative files not found at {NORMATIVE_DIR}. Set {ENV_VAR} to a local "
        "copy of the OMG RoIS Framework 2.0 machine-readable files."
    ),
)
