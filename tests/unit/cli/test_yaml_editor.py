import pytest
from pathlib import Path
from src.cli.widgets.yaml_editor import YamlEditor


@pytest.fixture
def fake_yaml(tmp_path: Path) -> Path:
    test_file = tmp_path / "test.yaml"
    data = """
# Комментарий, который не должен пропасть
system:
  enabled: true
  limits:
    max_retries: 5
  models:
    - gpt-4o
    - claude-3
"""
    test_file.write_text(data.strip(), encoding="utf-8")
    return test_file


def test_yaml_editor_load(fake_yaml: Path):
    """Тест: Редактор успешно грузит YAML в память."""
    editor = YamlEditor(fake_yaml)
    assert editor.data["system"]["enabled"] is True
    assert len(editor.data["system"]["models"]) == 2


def test_yaml_editor_navigation(fake_yaml: Path):
    """Тест: Стек навигации возвращает корректный текущий узел."""
    editor = YamlEditor(fake_yaml)

    # Проваливаемся в 'system'
    editor.current_path.append("system")
    node = editor._get_current_node()
    assert "enabled" in node
    assert editor._get_path_string() == "system"

    # Проваливаемся глубже в 'limits'
    editor.current_path.append("limits")
    node2 = editor._get_current_node()
    assert node2["max_retries"] == 5
    assert editor._get_path_string() == "system > limits"


def test_yaml_editor_save_preserves_comments(fake_yaml: Path):
    """Тест: Сохранение файла не удаляет комментарии (спасибо ruamel)."""
    editor = YamlEditor(fake_yaml)
    editor.data["system"]["enabled"] = False
    editor._save()

    content = fake_yaml.read_text(encoding="utf-8")
    assert "enabled: false" in content
    assert "# Комментарий, который не должен пропасть" in content
