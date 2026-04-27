from pathlib import Path


def is_ignored(path: Path) -> bool:
    """Единый фильтр мусора. Отсекает кэш, логи, скрытые файлы и виртуальные окружения."""
    ignore_dirs = {
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".git",
    }
    ignore_exts = {".pyc", ".pyo", ".pyd", ".tmp", ".swp"}

    if path.suffix in ignore_exts or path.name.endswith("~"):
        return True

    for part in path.parts:
        if part in ignore_dirs:
            return True
        # Игнорируем скрытые папки/файлы, но оставляем .env на случай, если он нужен в песочнице
        if part.startswith(".") and part not in {".", ".env"}:
            return True

    return False
