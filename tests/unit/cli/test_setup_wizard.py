from pathlib import Path
from unittest.mock import patch

from src.cli.screens.setup_wizard import _ensure_yaml_exists


def test_ensure_yaml_exists_copies_example(tmp_path: Path):
    """Тест: Если целевого конфига нет, но есть шаблон (.example), он копируется."""

    # Создаем фейковый .example.yaml
    example_file = tmp_path / "settings.example.yaml"
    example_file.write_text("test: data", encoding="utf-8")

    # Мокаем CONFIG_DIR на нашу временную папку
    with patch("src.cli.screens.setup_wizard.CONFIG_DIR", tmp_path):
        target_path = _ensure_yaml_exists("settings.yaml")

        assert target_path is not None
        assert target_path.exists()
        assert target_path.read_text(encoding="utf-8") == "test: data"


def test_ensure_yaml_exists_no_template(tmp_path: Path):
    """Тест: Если нет ни конфига, ни шаблона, возвращается None."""

    with patch("src.cli.screens.setup_wizard.CONFIG_DIR", tmp_path):
        target_path = _ensure_yaml_exists("missing.yaml")
        assert target_path is None
