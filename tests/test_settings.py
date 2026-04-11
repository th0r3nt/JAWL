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


def test_host_pc_config_defaults():
    """Тест: Pydantic-модель HostOSConfig правильно подставляет дефолтные значения."""
    # Передаем только часть данных, остальное должно заполниться по умолчанию
    config = HostOSConfig(madness_level=3)

    assert config.madness_level == 3
    assert config.enabled is True
    assert config.file_read_max_lines == 5000  # Дефолтное значение


def test_host_pc_config_validation():
    """Тест: Pydantic-модель выбрасывает ошибку при неверных типах."""
    with pytest.raises(ValueError):
        # Передаем строку вместо числа
        HostOSConfig(monitoring_interval_sec="not_a_number")
