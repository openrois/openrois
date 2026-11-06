#!/usr/bin/env python3
"""Rebuild the assemblies bundled in Runtime/Plugins, or check the committed ones.

    python3 sdk/unity/scripts~/bundle_dlls.py          rewrite Runtime/Plugins
    python3 sdk/unity/scripts~/bundle_dlls.py --check  fail if Runtime/Plugins differs

The script needs the .NET SDK pinned in global.json beside it, and NuGet access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent
PLUGINS_DIR = PACKAGE_DIR / "Runtime" / "Plugins"
PROJECT_NAME = "OpenRoIS.Interfaces"
PROJECT = (
    PACKAGE_DIR.parent.parent
    / "interfaces"
    / "csharp"
    / "src"
    / PROJECT_NAME
    / f"{PROJECT_NAME}.csproj"
)
TARGET_FRAMEWORK = ".NETStandard,Version=v2.1"

# Everything that restore resolves must be in exactly one of these two sets, so a
# System.Text.Json upgrade that adds a dependency stops here for a decision.
BUNDLED = {
    "Microsoft.Bcl.AsyncInterfaces",
    "System.IO.Pipelines",
    "System.Runtime.CompilerServices.Unsafe",
    "System.Text.Encodings.Web",
    "System.Text.Json",
}
PROVIDED_BY_UNITY = {
    "System.Buffers",
    "System.Memory",
    "System.Numerics.Vectors",
    "System.Threading.Tasks.Extensions",
}

# The public API of OpenRoIS.Sdk exposes JsonElement, so code that uses the SDK has
# to see System.Text.Json. The other assemblies stay out of user assemblies.
AUTO_REFERENCED = {PROJECT_NAME, "System.Text.Json"}

PLUGIN_META = """\
fileFormatVersion: 2
guid: {guid}
PluginImporter:
  externalObjects: {{}}
  serializedVersion: 2
  iconMap: {{}}
  executionOrder: {{}}
  defineConstraints: []
  isPreloaded: 0
  isOverridable: 0
  isExplicitlyReferenced: {explicit}
  validateReferences: 1
  platformData:
  - first:
      Any: 
    second:
      enabled: 1
      settings: {{}}
  - first:
      Editor: Editor
    second:
      enabled: 0
      settings:
        DefaultValueInitialized: true
  - first:
      Windows Store Apps: WindowsStoreApps
    second:
      enabled: 0
      settings:
        CPU: AnyCPU
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""

TEXT_META = """\
fileFormatVersion: 2
guid: {guid}
TextScriptImporter:
  externalObjects: {{}}
  userData: 
  assetBundleName: 
  assetBundleVariant: 
"""


def stable_guid(file_name: str) -> str:
    """Derive the GUID from the file name, so a rebuild never changes a .meta file."""
    return hashlib.md5(f"org.openrois.sdk/Runtime/Plugins/{file_name}".encode()).hexdigest()


def build_project(artifacts: Path) -> Path:
    """Build the interface types and return the folder that holds the output.

    The properties leave out what varies between commits and checkouts: the commit
    hash in the informational version, and the source paths in the debug information.
    """
    subprocess.run(
        [
            "dotnet",
            "build",
            str(PROJECT),
            "--configuration",
            "Release",
            "--artifacts-path",
            str(artifacts),
            "--verbosity",
            "quiet",
            "-p:DebugType=none",
            "-p:ContinuousIntegrationBuild=true",
            "-p:EnableSourceLink=false",
            "-p:IncludeSourceRevisionInInformationalVersion=false",
        ],
        cwd=SCRIPT_DIR,
        check=True,
    )
    return artifacts / "bin" / PROJECT_NAME / "release"


def resolve_third_party(artifacts: Path) -> list[Path]:
    """Return the restored DLL of every assembly in BUNDLED."""
    assets_file = artifacts / "obj" / PROJECT_NAME / "project.assets.json"
    assets = json.loads(assets_file.read_text(encoding="utf-8"))
    package_folders = [Path(folder) for folder in assets["packageFolders"]]

    dlls: dict[str, Path] = {}
    for library, target in assets["targets"][TARGET_FRAMEWORK].items():
        name = library.split("/")[0]
        if name in PROVIDED_BY_UNITY:
            continue
        if name not in BUNDLED:
            sys.exit(f"{library} is new: add it to BUNDLED or PROVIDED_BY_UNITY.")
        relative_dir = assets["libraries"][library]["path"]
        for runtime_path in target["runtime"]:
            for folder in package_folders:
                candidate = folder / relative_dir / runtime_path
                if candidate.is_file():
                    dlls[name] = candidate

    missing = BUNDLED - dlls.keys()
    if missing:
        sys.exit(f"Restore did not resolve: {', '.join(sorted(missing))}")
    return [dlls[name] for name in sorted(dlls)]


def write_plugin(source: Path, staging: Path) -> None:
    """Copy one DLL to the staging folder, with its .meta file."""
    shutil.copyfile(source, staging / source.name)
    meta = PLUGIN_META.format(
        guid=stable_guid(source.name),
        explicit=0 if source.stem in AUTO_REFERENCED else 1,
    )
    (staging / f"{source.name}.meta").write_text(meta, encoding="utf-8", newline="\n")


def write_staging(artifacts: Path, staging: Path) -> None:
    """Fill the staging folder with the expected content of Runtime/Plugins."""
    output = build_project(artifacts)
    for dll in [output / f"{PROJECT_NAME}.dll", *resolve_third_party(artifacts)]:
        write_plugin(dll, staging)

    xml_name = f"{PROJECT_NAME}.xml"
    shutil.copyfile(output / xml_name, staging / xml_name)
    (staging / f"{xml_name}.meta").write_text(
        TEXT_META.format(guid=stable_guid(xml_name)), encoding="utf-8", newline="\n"
    )


def differences(staging: Path) -> list[str]:
    """List the files of Runtime/Plugins that do not match the staging folder."""
    expected = {path.name for path in staging.iterdir()}
    committed = {path.name for path in PLUGINS_DIR.iterdir()} if PLUGINS_DIR.is_dir() else set()
    report = [f"missing: {name}" for name in sorted(expected - committed)]
    report += [f"unexpected: {name}" for name in sorted(committed - expected)]
    for name in sorted(expected & committed):
        if (staging / name).read_bytes() != (PLUGINS_DIR / name).read_bytes():
            report.append(f"differs: {name}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp:
        artifacts = Path(temp) / "artifacts"
        staging = Path(temp) / "staging"
        staging.mkdir()
        write_staging(artifacts, staging)

        report = differences(staging)
        if not report:
            print(f"Runtime/Plugins is up to date ({len(list(staging.iterdir()))} files).")
            return 0
        if args.check:
            print("\n".join(report))
            print("Runtime/Plugins is out of date. Run: python3 sdk/unity/scripts~/bundle_dlls.py")
            return 1

        shutil.rmtree(PLUGINS_DIR, ignore_errors=True)
        shutil.copytree(staging, PLUGINS_DIR)
        print(f"Runtime/Plugins rewritten: {len(report)} changes.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
