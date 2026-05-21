import pytest
import yaml
from pathlib import Path
from yaml.constructor import ConstructorError
from unittest.mock import patch

from src.utils.settings import (
    load_yaml,
    load_config,
    HostOSConfig,
    _log_missing_defaults,
    SystemConfig,
)


def test_load_yaml_success(tmp_path: Path):
    """Test: load_yaml parses YAML correctly."""
    test_file = tmp_path / "test.yaml"

    test_data = {"host_pc": {"enabled": True, "access_level": 2}}
    with open(test_file, "w", encoding="utf-8") as f:
        yaml.dump(test_data, f)

    result = load_yaml(test_file)
    assert result["host_pc"]["access_level"] == 2


def test_load_yaml_file_not_found():
    """Test: FileNotFound raises correct exception."""
    fake_path = Path("/this/file/does/not/exist.yaml")

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_yaml(fake_path)


def test_host_os_config_parsing():
    """Test: Pydantic model parses valid data."""
    data = {
        "enabled": True,
        "access_level": 3,
        "env_access": False,
        "monitoring_interval_sec": 30,
        "execution_timeout_sec": 60,
        "file_read_max_chars": 5000,
        "file_list_limit": 100,
        "http_response_max_chars": 5000,
        "top_processes_limit": 10,
    }
    config = HostOSConfig(**data)

    assert config.access_level == 3
    assert config.enabled is True
    assert config.file_read_max_chars == 5000


def test_host_os_config_validation():
    """Test: ValidationError on wrong types."""
    data = {
        "enabled": True,
        "access_level": 3,
        "env_access": False,
        "monitoring_interval_sec": "not_a_number",
        "execution_timeout_sec": 60,
        "file_read_max_chars": 5000,
        "file_list_limit": 100,
        "http_response_max_chars": 5000,
        "top_processes_limit": 10,
    }
    with pytest.raises(ValueError):
        HostOSConfig(**data)


def test_load_yaml_duplicate_keys(tmp_path: Path):
    """Test: duplicate keys raise ConstructorError."""
    test_file = tmp_path / "test_dup.yaml"

    test_data = """
system:
  timezone: 3
system:
  timezone: 5
    """
    test_file.write_text(test_data.strip(), encoding="utf-8")

    with pytest.raises(ConstructorError, match="Duplicate key 'system'"):
        load_yaml(test_file)


def test_log_missing_defaults():
    """Test: recursively logs missing keys set to defaults."""

    partial_config = SystemConfig.model_validate({"timezone": 3})

    with patch("src.utils.settings.main_logger.debug") as mock_debug:
        _log_missing_defaults(partial_config, prefix="", file_name="settings.yaml")

        assert mock_debug.call_count >= 1

        log_messages = " ".join([call[0][0] for call in mock_debug.call_args_list])

        assert "settings.yaml" in log_messages
        assert "'heartbeat_interval'" in log_messages
        assert "'continuous_cycle'" in log_messages
        assert "'event_acceleration.critical_multiplier'" in log_messages


def test_load_config_auto_recover(tmp_path):
    """Test: load_config recovers .yaml files from .example.yaml."""

    with patch("src.utils.settings.Path.cwd", return_value=tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        settings_example = config_dir / "settings.example.yaml"
        settings_example.write_text(
            "identity:\n  agent_name: 'RecoveredAgent'\n", encoding="utf-8"
        )

        interfaces_example = config_dir / "interfaces.example.yaml"
        interfaces_example.write_text("host:\n  os:\n    enabled: true\n", encoding="utf-8")

        assert not (config_dir / "settings.yaml").exists()

        settings, interfaces = load_config()

        assert (config_dir / "settings.yaml").exists()
        assert (config_dir / "interfaces.yaml").exists()

        assert settings.identity.agent_name == "RecoveredAgent"
        assert interfaces.host.os.enabled is True
