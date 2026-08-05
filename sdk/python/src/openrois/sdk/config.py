"""Load and validate robot-adapter YAML config files.

The config file declares the adapter's components, fleet_id, and connection
info. The adapter reads it at startup and sends the component list to the
avatar via the registration protocol.

The default config file name is not hardcoded here. The caller passes the
path. The adapter SDK's CLI (framework.py) accepts --config <path>.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str | Path) -> dict[str, object]:
    """Load a robot-adapter YAML config file.

    Args:
        path: Path to the YAML file.

    Returns:
        A dict with keys:
            fleet_id: str
            connection: dict (with ws: {host, port})
            components: list[dict] (optional, for reference)

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        ValueError: If the top-level YAML is not a mapping.
    """
    path = Path(path)
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"Config file {path} must contain a YAML mapping at the top level",
        )
    return data
