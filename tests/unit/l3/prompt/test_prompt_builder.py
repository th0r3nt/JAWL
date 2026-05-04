import pytest
from unittest.mock import patch
from pathlib import Path

from src.l3_agent.prompt.builder import PromptBuilder


# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def fake_prompt_dir(tmp_path: Path) -> Path:
    """Создает тестовую структуру папок и файлов промпта."""
    # Создаем директории
    personality_dir = tmp_path / "personality"
    personality_dir.mkdir()

    system_dir = tmp_path / "system"
    system_dir.mkdir()

    # Файлы личности (один из них - пример, должен быть проигнорирован)
    # Называем их a_ и b_, чтобы проверить сортировку (builder должен склеивать по алфавиту)
    (personality_dir / "a_soul.md").write_text("Я - агент.", encoding="utf-8")
    (personality_dir / "b_ignore.example.md").write_text(
        "Этот текст не должен попасть.", encoding="utf-8"
    )
    (personality_dir / "c_traits.md").write_text("Я - ленивый.", encoding="utf-8")

    # Файлы системы
    (system_dir / "rules.md").write_text("Системное правило: не спамить.", encoding="utf-8")

    return tmp_path


# ===================================================================
# TESTS
# ===================================================================


def test_prompt_builder_happy_path(fake_prompt_dir):
    builder = PromptBuilder(fake_prompt_dir)
    result = builder.build()

    assert "Я - агент." in result
    assert "Я - ленивый." in result
    assert "Системное правило: не спамить." in result
    assert "Этот текст не должен попасть." not in result


def test_prompt_builder_missing_folders(tmp_path):
    builder = PromptBuilder(tmp_path)
    result = builder.build()
    assert result == ""  # Папок нет, промпт пустой


def test_prompt_builder_read_error(fake_prompt_dir):
    builder = PromptBuilder(fake_prompt_dir)
    with patch("pathlib.Path.read_text", side_effect=PermissionError("Отказано в доступе")):
        with pytest.raises(RuntimeError) as exc:
            builder.build()
        assert "Ошибка чтения файла промпта" in str(exc.value)
