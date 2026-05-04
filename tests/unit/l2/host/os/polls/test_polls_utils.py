from pathlib import Path
from src.l2_interfaces.host.os.polls.utils import is_ignored


def test_is_ignored():
    """Тест: функция фильтрации директорий и мусора работает корректно."""
    # Очевидный мусор
    assert is_ignored(Path("venv/lib/os.py")) is True
    assert is_ignored(Path("sandbox/node_modules/package.json")) is True
    assert is_ignored(Path("sandbox/__pycache__/script.cpython-310.pyc")) is True

    # Скрытые папки и файлы (кроме .env)
    assert is_ignored(Path("sandbox/.hidden_folder/file.txt")) is True
    assert is_ignored(Path("sandbox/.gitignore")) is True
    assert is_ignored(Path("sandbox/file.py~")) is True

    # Расширения
    assert is_ignored(Path("sandbox/script.pyc")) is True

    # Важные исключения (ОБЯЗАНЫ ПРОХОДИТЬ)
    assert is_ignored(Path("sandbox/.env")) is False
    assert is_ignored(Path("sandbox/main.py")) is False
    assert is_ignored(Path("sandbox/folder/app.js")) is False
