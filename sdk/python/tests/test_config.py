"""Tests for the config loader."""

from __future__ import annotations

import pytest

from openrois.sdk.config import load_config


def test_load_valid_config(tmp_path):
    """load_config returns a dict from a valid YAML file."""
    config_file = tmp_path / "openrois-profile.yaml"
    config_file.write_text(
        "engine_id: robot_1\n"
        "connection:\n"
        "  ws:\n"
        "    host: 127.0.0.1\n"
        "    port: 8765\n"
        "components:\n"
        "  - ref: SystemInformation\n"
        "    type: basic\n"
        "    bind_required: false\n"
        "    queries: [robot_position]\n",
    )
    config = load_config(config_file)
    assert config["engine_id"] == "robot_1"
    assert config["connection"]["ws"]["port"] == 8765
    assert len(config["components"]) == 1
    assert config["components"][0]["ref"] == "SystemInformation"


def test_load_missing_file(tmp_path):
    """load_config raises FileNotFoundError for a missing file."""
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_non_mapping(tmp_path):
    """load_config raises ValueError for a non-mapping YAML."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(config_file)


def test_load_empty_file(tmp_path):
    """load_config raises ValueError for an empty file (None from YAML)."""
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("")
    with pytest.raises(ValueError, match="mapping"):
        load_config(config_file)
