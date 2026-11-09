"""Configuration: defaults, the YAML file, the environment and flags, in that order."""

from __future__ import annotations

from pathlib import Path

import pytest

from openrois.gateway import ConfigError, GatewayConfig, parse_config


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_the_defaults_bind_loopback_on_8765() -> None:
    assert parse_config([], {}) == GatewayConfig(
        host="127.0.0.1", port=8765, engine_id="gateway", log_level="info", child_timeout=10.0
    )


def test_the_file_overrides_the_defaults(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "port: 9000\nengine_id: lab\n")
    config = parse_config(["--config", str(config_file)], {})
    assert (config.port, config.engine_id, config.host) == (9000, "lab", "127.0.0.1")


def test_the_environment_names_the_file(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "port: 9000\n")
    config = parse_config([], {"OPENROIS_GATEWAY_CONFIG": str(config_file)})
    assert config.port == 9000


def test_the_environment_overrides_the_file(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "port: 9000\nhost: 0.0.0.0\n")
    environ = {
        "OPENROIS_GATEWAY_CONFIG": str(config_file),
        "OPENROIS_GATEWAY_PORT": "9100",
        "OPENROIS_GATEWAY_CHILD_TIMEOUT": "2.5",
    }
    config = parse_config([], environ)
    assert (config.port, config.host, config.child_timeout) == (9100, "0.0.0.0", 2.5)


def test_flags_override_the_environment(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "log_level: warning\n")
    environ = {"OPENROIS_GATEWAY_PORT": "9100", "OPENROIS_GATEWAY_LOG_LEVEL": "error"}
    argv = ["--config", str(config_file), "--port", "9200", "--log-level", "DEBUG"]
    config = parse_config(argv, environ)
    assert (config.port, config.log_level) == (9200, "debug")


def test_an_empty_file_keeps_the_defaults(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "")
    assert parse_config(["--config", str(config_file)], {}) == GatewayConfig()


@pytest.mark.parametrize(
    ("argv", "environ", "message"),
    [
        (["--port", "70000"], {}, "port: Input should be less than or equal to 65535"),
        ([], {"OPENROIS_GATEWAY_PORT": "eighty"}, "port: Input should be a valid integer"),
        (["--engine-id", "a/b"], {}, "engine_id: Value error, must not contain a slash"),
        (["--child-timeout", "0"], {}, "child_timeout: Input should be greater than 0"),
        ([], {"OPENROIS_GATEWAY_LOG_LEVEL": "loud"}, "log_level: Input should be"),
    ],
)
def test_invalid_settings_are_named(argv: list[str], environ: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match="Invalid configuration") as info:
        parse_config(argv, environ)
    assert message in str(info.value)


def test_an_unknown_key_in_the_file_is_an_error(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "prot: 9000\n")
    with pytest.raises(ConfigError, match="prot: Extra inputs are not permitted"):
        parse_config(["--config", str(config_file)], {})


def test_a_file_that_is_not_a_mapping_is_an_error(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "- port\n")
    with pytest.raises(ConfigError, match="must hold a mapping"):
        parse_config(["--config", str(config_file)], {})


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Cannot read"):
        parse_config(["--config", str(tmp_path / "absent.yaml")], {})


def test_a_file_that_is_not_yaml_is_an_error(tmp_path: Path) -> None:
    config_file = write(tmp_path / "gateway.yaml", "port: [9000\n")
    with pytest.raises(ConfigError, match="is not valid YAML"):
        parse_config(["--config", str(config_file)], {})
