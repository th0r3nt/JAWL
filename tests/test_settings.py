import pytest
import yaml
from pathlib import Path

from src.utils.settings import (
    load_yaml,
    HostOSConfig,
)


def test_load_yaml_success(tmp_path: Path):
    """Тест: функция load_yaml корректно читает и парсит YAML."""
    test_file = tmp_path / "test.yaml"

    # Создаем временный yaml файл
    test_data = {"host_pc": {"enabled": True, "madness_level": 2}}
    with open(test_file, "w", encoding="utf-8") as f:
        yaml.dump(test_data, f)

    result = load_yaml(test_file)
    assert result["host_pc"]["madness_level"] == 2


def test_load_yaml_file_not_found():
    """Тест: попытка загрузить несуществующий файл вызывает ошибку."""
    fake_path = Path("/this/file/does/not/exist.yaml")

    with pytest.raises(FileNotFoundError, match="Конфигурационный файл не найден"):
        load_yaml(fake_path)


def test_host_os_config_parsing():
    """Тест: Pydantic-модель HostOSConfig правильно парсит валидные данные."""
    data = {
        "enabled": True,
        "madness_level": 3,
        "env_access": False,
        "monitoring_interval_sec": 30,
        "execution_timeout_sec": 60,
        "file_read_max_chars": 5000,
        "file_list_limit": 100,
        "http_response_max_chars": 5000,
        "top_processes_limit": 10,
    }
    config = HostOSConfig(**data)

    assert config.madness_level == 3
    assert config.enabled is True
    assert config.file_read_max_chars == 5000


def test_host_os_config_validation():
    """Тест: Pydantic-модель выбрасывает ошибку при неверных типах."""
    data = {
        "enabled": True,
        "madness_level": 3,
        "env_access": False,
        "monitoring_interval_sec": "not_a_number",  # Намеренная ошибка типа
        "execution_timeout_sec": 60,
        "file_read_max_chars": 5000,
        "file_list_limit": 100,
        "http_response_max_chars": 5000,
        "top_processes_limit": 10,
    }
    with pytest.raises(ValueError):
        HostOSConfig(**data)
