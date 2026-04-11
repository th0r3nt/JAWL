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
    """Тест: успешная склейка, игнор .example.md и правильный порядок блоков."""
    builder = PromptBuilder(fake_prompt_dir)

    skills_docs = "mock_skill() - тестовая функция."

    result = builder.build(skills_docs)

    # Проверяем, что нужный текст попал в промпт
    assert "Я - агент." in result
    assert "Я - ленивый." in result
    assert "Системное правило: не спамить." in result
    assert "SKILLS LIBRARY\nmock_skill() - тестовая функция." in result

    # Проверяем игнор .example.md
    assert "Этот текст не должен попасть." not in result

    # Проверяем порядок (a_soul.md должен быть перед c_traits.md)
    idx_soul = result.find("Я - агент.")
    idx_traits = result.find("Я - ленивый.")
    assert idx_soul < idx_traits


def test_prompt_builder_missing_folders(tmp_path):
    """Тест: если папок personality и system нет, система не падает, а возвращает только скиллы."""
    # tmp_path - это пустая папка, там нет подпапок.
    builder = PromptBuilder(tmp_path)

    result = builder.build("only_skills_here")

    assert "SKILLS LIBRARY" in result
    assert "only_skills_here" in result


def test_prompt_builder_read_error(fake_prompt_dir):
    """
    Тест: если файл не читается (например, нет прав),
    система должна выбросить кастомный RuntimeError.
    """
    builder = PromptBuilder(fake_prompt_dir)

    # Подменяем функцию read_text так, чтобы она всегда кидала ошибку
    with patch("pathlib.Path.read_text", side_effect=PermissionError("Отказано в доступе")):
        with pytest.raises(RuntimeError) as exc:
            builder.build("skills")

        # Проверяем текст ошибки
        assert "Ошибка чтения файла промпта" in str(exc.value)
        assert "Отказано в доступе" in str(exc.value)
