#!/usr/bin/env python3
"""Print the notes of a GitHub release from the CHANGELOG sections of one version.

Each --part names a CHANGELOG, the version as that CHANGELOG spells it, and an optional
heading. A package released in several languages passes one part with a heading for each,
and they come out as headed sections between lines of ---. A package with one part and no
heading comes out as the body of its section, with nothing added.

The version heading is left out, because the release title already says it. A missing or
empty section exits non-zero, so that a release cannot go out without its notes.

Usage:
    python3 .github/scripts/release_notes.py --part engine/CHANGELOG.md 0.1.0a2

    python3 .github/scripts/release_notes.py \\
        --part interfaces/python/CHANGELOG.md 0.1.0a6 "Python (openrois-interfaces)" \\
        --part interfaces/csharp/CHANGELOG.md 0.1.0-alpha.6 "C# (OpenRoIS.Interfaces)"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK_REFERENCE = re.compile(r"^\[[^\]]+\]:\s")
SEPARATOR = "\n\n---\n\n"


def section(path: Path, version: str) -> str:
    """Return the body of the section of ``version``, without its heading."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        sys.exit(f"::error::{path}: {error.strerror}")

    heading = re.compile(rf"^## (?:\[{re.escape(version)}\]|{re.escape(version)})(?:\s|$)")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        sys.exit(f"::error::{path} has no section for {version}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    body = lines[start + 1 : end]

    # The link references close the file, so they follow the last section with no heading
    # of their own to stop at.
    while body and (not body[-1].strip() or LINK_REFERENCE.match(body[-1])):
        body.pop()
    while body and not body[0].strip():
        body.pop(0)

    # A section with only category headings left has nothing for a reader either.
    if not any(line.strip() and not line.startswith("#") for line in body):
        sys.exit(f"::error::{path} has an empty section for {version}")
    return "\n".join(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--part",
        action="append",
        nargs="+",
        required=True,
        metavar="VALUE",
        help="a CHANGELOG path, the version as it spells it, and an optional heading",
    )
    args = parser.parse_args()

    parts = []
    for part in args.part:
        if len(part) not in (2, 3):
            parser.error(f"--part takes a path, a version and an optional heading, not {part}")
        body = section(Path(part[0]), part[1])
        parts.append(f"## {part[2]}\n\n{body}" if len(part) == 3 else body)
    print(SEPARATOR.join(parts))


if __name__ == "__main__":
    main()
