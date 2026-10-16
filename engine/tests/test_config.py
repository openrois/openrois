"""The configuration loader: defaults, the YAML file, the environment and flags, in order."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from openrois.engine.config import AdapterConfig, ConfigError, load_adapter_config, load_config


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class Speech(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    voice: str = "default"
    volume: float = 1.0


class RobotConfig(AdapterConfig):
    """An adapter with one component section and an engine id of its own."""

    engine_id: str = "robot"
    speech: Speech = Speech()


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    port: int = 1
    name: str = "a"
    nested: Speech = Speech()


class TestLoadConfig:
    """The generic loader, which the gateway and every adapter share."""

    def test_the_defaults(self) -> None:
        assert load_config(Settings, env_prefix="X_", names=["port"], environ={}) == Settings()

    def test_each_source_overrides_the_one_before(self, tmp_path: Path) -> None:
        config_file = write(tmp_path / "x.yaml", "port: 2\nname: file\n")
        config = load_config(
            Settings,
            env_prefix="X_",
            names=["port", "name"],
            environ={"X_PORT": "3", "X_NAME": "env"},
            config_file=config_file,
            flags={"port": 4, "name": None},
        )
        # An absent flag, None, leaves the environment's value in place.
        assert (config.port, config.name) == (4, "env")

    def test_the_environment_names_the_file(self, tmp_path: Path) -> None:
        config_file = write(tmp_path / "x.yaml", "port: 2\n")
        environ = {"X_CONFIG": str(config_file)}
        assert load_config(Settings, env_prefix="X_", names=[], environ=environ).port == 2

    def test_a_named_file_wins_over_the_environment(self, tmp_path: Path) -> None:
        named = write(tmp_path / "named.yaml", "port: 2\n")
        other = write(tmp_path / "other.yaml", "port: 3\n")
        config = load_config(
            Settings,
            env_prefix="X_",
            names=[],
            environ={"X_CONFIG": str(other)},
            config_file=named,
        )
        assert config.port == 2

    def test_only_the_named_settings_come_from_the_environment(self) -> None:
        config = load_config(
            Settings, env_prefix="X_", names=["port"], environ={"X_PORT": "5", "X_NAME": "b"}
        )
        assert (config.port, config.name) == (5, "a")

    def test_sections_come_from_the_file(self, tmp_path: Path) -> None:
        config_file = write(tmp_path / "x.yaml", "nested:\n  voice: calm\n")
        config = load_config(
            Settings, env_prefix="X_", names=[], environ={}, config_file=config_file
        )
        assert config.nested == Speech(voice="calm")

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("prot: 2\n", "prot: Extra inputs are not permitted"),
            ("nested:\n  voise: calm\n", "nested.voise: Extra inputs are not permitted"),
            ("port: two\n", "port: Input should be a valid integer"),
            ("- port\n", "must hold a mapping"),
            ("port: [2\n", "is not valid YAML"),
        ],
    )
    def test_a_bad_file_is_named(self, tmp_path: Path, text: str, message: str) -> None:
        config_file = write(tmp_path / "x.yaml", text)
        with pytest.raises(ConfigError, match=message.replace("[", r"\[")):
            load_config(Settings, env_prefix="X_", names=[], environ={}, config_file=config_file)

    def test_a_missing_file_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Cannot read"):
            load_config(
                Settings,
                env_prefix="X_",
                names=[],
                environ={},
                config_file=tmp_path / "absent.yaml",
            )


class TestAdapterConfig:
    def test_the_defaults(self) -> None:
        config = load_adapter_config(RobotConfig, [], {})
        assert config == RobotConfig(
            gateway_url="ws://127.0.0.1:8765",
            engine_id="robot",
            robot_address=None,
            log_level="info",
            speech=Speech(),
        )

    def test_the_file_is_adapter_yaml_through_the_flag_or_the_environment(
        self, tmp_path: Path
    ) -> None:
        config_file = write(tmp_path / "adapter.yaml", "engine_id: lab\nspeech:\n  volume: 0.5\n")
        by_flag = load_adapter_config(RobotConfig, ["--config", str(config_file)], {})
        by_env = load_adapter_config(RobotConfig, [], {"OPENROIS_ADAPTER_CONFIG": str(config_file)})
        assert by_flag == by_env
        assert (by_flag.engine_id, by_flag.speech.volume) == ("lab", 0.5)

    def test_the_four_common_settings_come_from_the_environment_and_flags(
        self, tmp_path: Path
    ) -> None:
        config_file = write(
            tmp_path / "adapter.yaml",
            "gateway_url: ws://file:1\nengine_id: file\nrobot_address: 10.0.0.1\n",
        )
        environ = {
            "OPENROIS_ADAPTER_CONFIG": str(config_file),
            "OPENROIS_ADAPTER_GATEWAY_URL": "ws://env:2",
            "OPENROIS_ADAPTER_ENGINE_ID": "env",
            "OPENROIS_ADAPTER_ROBOT_ADDRESS": "10.0.0.2",
            "OPENROIS_ADAPTER_LOG_LEVEL": "warning",
        }
        argv = ["--engine-id", "flag", "--robot-address", "10.0.0.3", "--log-level", "DEBUG"]
        config = load_adapter_config(RobotConfig, argv, environ)
        assert (config.gateway_url, config.engine_id, config.robot_address, config.log_level) == (
            "ws://env:2",
            "flag",
            "10.0.0.3",
            "debug",
        )

    def test_component_sections_do_not_come_from_the_environment(self) -> None:
        environ = {"OPENROIS_ADAPTER_SPEECH": "loud"}
        assert load_adapter_config(RobotConfig, [], environ).speech == Speech()

    def test_a_flag_for_a_component_setting_does_not_exist(self) -> None:
        with pytest.raises(SystemExit):
            load_adapter_config(RobotConfig, ["--speech", "loud"], {})

    def test_the_base_needs_an_engine_id(self) -> None:
        with pytest.raises(ConfigError, match="engine_id: Field required"):
            load_adapter_config(AdapterConfig, [], {})

    @pytest.mark.parametrize("engine_id", ["a/b", ""])
    def test_an_engine_id_needs_characters_and_no_slash(self, engine_id: str) -> None:
        with pytest.raises(ConfigError, match="engine_id"):
            load_adapter_config(RobotConfig, ["--engine-id", engine_id], {})

    def test_an_unknown_log_level_is_named(self) -> None:
        environ = {"OPENROIS_ADAPTER_LOG_LEVEL": "loud"}
        with pytest.raises(ConfigError, match="log_level: Input should be"):
            load_adapter_config(RobotConfig, [], environ)
