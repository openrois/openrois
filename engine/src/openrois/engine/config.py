"""Profile YAML reading and per-component config merging.

read_profile reads a YAML file and returns a dict.
component_config builds a per-component config dict from a profile,
matching the merge order of the existing RobotAdapter._init_components:
engine section (lowest priority), then environment, then per-component
section (highest priority). The "engine" key is also included as a
nested dict so components can access config.get("engine", {}).get("id").
"""

from __future__ import annotations

import yaml


def read_profile(path: str) -> dict:
    """Read profile YAML and return a config dict.

    Args:
        path: Path to the YAML file.

    Returns:
        A dict with the YAML contents.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    with open(path) as f:
        return yaml.safe_load(f)


def component_config(profile: dict, ref: str) -> dict:
    """Build per-component config dict from profile.

    Merges engine section (lowest priority) + environment + per-component
    section (highest priority), matching the existing
    RobotAdapter._init_components merge order. The "engine" key is
    also included as a nested dict so components can access
    config.get("engine", {}).get("id").

    Args:
        profile: The full profile dict from read_profile.
        ref: The component ref (e.g., "Navigation").

    Returns:
        A merged config dict for the component.
    """
    return {
        **profile.get("engine", {}),
        **profile.get("environment", {}),
        **profile.get("components", {}).get(ref, {}),
        "engine": profile.get("engine", {}),
    }