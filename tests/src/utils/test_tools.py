import pytest
from pathlib import Path
from src.utils._tools import (
    format_size,
    validate_sandbox_path,
    truncate_text,
    parse_int_or_str,
)


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1500) == "1.5 KB"
    assert format_size(1500000) == "1.4 MB"
    assert format_size(5 * 1024 ** 3) == "5.0 GB"
    assert format_size(2 * 1024 ** 4) == "2.0 TB"
    assert format_size(-2048) == "-2.0 KB"


def test_truncate_text():
    text = "Hello, world!"
    # Текст меньше лимита
    assert truncate_text(text, 50) == "Hello, world!"
    # Текст больше лимита
    assert truncate_text(text, 5) == "Hello\n... [Вывод обрезан. Превышен лимит символов]"


def test_parse_int_or_str():
    assert parse_int_or_str("12345") == 12345
    assert parse_int_or_str(12345) == 12345
    assert parse_int_or_str("@username") == "@username"


def test_validate_sandbox_path():
    cwd = Path.cwd()
    sandbox = cwd / "sandbox"

    # 1. Обычное имя файла
    res = validate_sandbox_path("test.txt")
    assert res == sandbox / "test.txt"

    # 2. Путь с указанием sandbox/
    res = validate_sandbox_path("sandbox/test.txt")
    assert res == sandbox / "test.txt"

    # 3. Path Traversal атака агента (попытка выйти из песочницы)
    with pytest.raises(PermissionError, match="Доступ запрещен"):
        validate_sandbox_path("../secret.env")
