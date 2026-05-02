"""
Unit-тесты для глобальных утилит (src/utils/_tools.py).

Особое внимание уделяется функции `validate_sandbox_path` (Gatekeeper),
чтобы гарантировать невозможность выхода за пределы песочницы (Path Traversal),
и функции `clean_html`, проверяя обработку XSS-векторов и мусорных тегов.
"""

import pytest
from pathlib import Path

from src.utils._tools import (
    format_size,
    parse_int_or_str,
    truncate_text,
    clean_html,
    validate_sandbox_path,
    draw_image_grid,
)


def test_format_size() -> None:
    """Проверяет корректность перевода байтов в человекочитаемый формат."""
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024 * 5.5) == "5.5 MB"
    assert format_size(-1024) == "-1.0 KB"


def test_parse_int_or_str() -> None:
    """Проверяет умный каст ID из Telegram."""
    assert parse_int_or_str("12345") == 12345
    assert parse_int_or_str(12345) == 12345
    assert parse_int_or_str("@username") == "@username"
    assert parse_int_or_str("  @username  ") == "@username"


def test_truncate_text() -> None:
    """Проверяет обрезку длинных текстов для защиты контекста LLM."""
    text = "Hello World!"
    # Не режет, если лимит больше текста
    assert truncate_text(text, 50) == "Hello World!"
    # Режет с добавлением суффикса
    truncated = truncate_text(text, 5, suffix="...")
    assert truncated == "Hello..."


class TestHTMLCleaner:
    """Группа тестов для проверки регулярных выражений очистки HTML."""

    def test_clean_html_removes_scripts_and_styles(self) -> None:
        """Скрипты и стили должны вырезаться вместе с содержимым."""
        html = "<html><style>body {color: red;}</style><script>alert('xss');</script><body>Text</body></html>"
        cleaned = clean_html(html)
        assert "alert" not in cleaned
        assert "color: red" not in cleaned
        assert cleaned == "Text"

    def test_clean_html_unescapes_entities(self) -> None:
        """HTML-сущности (&amp;, &quot;) должны корректно декодироваться."""
        html = "<p>Tom &amp; Jerry said &quot;Hi&quot; &#39;today&#39;</p>"
        cleaned = clean_html(html)
        assert cleaned == "Tom & Jerry said \"Hi\" 'today'"

    def test_clean_html_collapses_whitespace(self) -> None:
        """Множественные пробелы и переносы должны схлопываться."""
        html = "<div>Line 1</div>    \n\n  <div>Line 2</div>"
        cleaned = clean_html(html)
        assert cleaned == "Line 1 Line 2"


class TestGatekeeper:
    """
    Группа тестов для функции `validate_sandbox_path`.
    Критически важный тест безопасности (защита от Path Traversal).
    """

    def test_validate_sandbox_path_valid_files(self) -> None:
        """Разрешенные пути внутри песочницы должны успешно резолвиться."""
        sandbox_dir = (Path.cwd() / "sandbox").resolve()

        # Обычный файл
        path1 = validate_sandbox_path("test.txt")
        assert path1 == sandbox_dir / "test.txt"

        # С префиксом sandbox/
        path2 = validate_sandbox_path("sandbox/folder/test.txt")
        assert path2 == sandbox_dir / "folder" / "test.txt"

    def test_validate_sandbox_path_blocks_traversal(self) -> None:
        """Попытки выйти за пределы sandbox/ через '../' должны блокироваться."""
        with pytest.raises(PermissionError, match="Доступ запрещен"):
            validate_sandbox_path("../main.py")

        with pytest.raises(PermissionError, match="Доступ запрещен"):
            validate_sandbox_path("sandbox/../../etc/passwd")

    def test_validate_sandbox_path_blocks_absolute_paths(self) -> None:
        """Абсолютные пути за пределами песочницы должны блокироваться."""
        import os

        forbidden_path = "C:\\Windows\\System32" if os.name == "nt" else "/etc/passwd"

        with pytest.raises(PermissionError, match="Доступ запрещен"):
            validate_sandbox_path(forbidden_path)


# === НОВЫЕ ТЕСТЫ: ПРОВЕРКА PIL ИЗОБРАЖЕНИЙ ===


class TestImageGrid:
    """Группа тестов для алгоритма наложения координатной сетки."""

    def test_draw_image_grid_creates_correct_overlay(self, tmp_path):
        """Проверяет, что сетка накладывается без вылетов и корректно переводит картинку в RGB."""
        from PIL import Image

        # Создаем тестовое изображение
        test_img_path = tmp_path / "test_screenshot.png"
        img = Image.new("RGBA", (300, 300), color=(255, 255, 255, 255))
        img.save(test_img_path)

        # Вызываем функцию наложения сетки (шаг 100px)
        draw_image_grid(test_img_path, step=100)

        # Загружаем сохраненный результат и проверяем параметры
        with Image.open(test_img_path) as modified_img:
            # Изображение должно быть конвертировано в RGB для совместимости
            assert modified_img.mode == "RGB"
            assert modified_img.size == (300, 300)

            # Поскольку мы нарисовали линии с шагом 100, пиксель (100, 0)
            # должен быть красным (так как overlay линия (255, 0, 0, 80) легла на белый фон)
            r, g, b = modified_img.getpixel((100, 0))
            assert r == 255  # Красный канал максимальный
            assert g < 255  # Зеленый просел из-за альфа-канала (краска легла)
            assert b < 255  # Синий просел
