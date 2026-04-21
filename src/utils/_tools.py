import psutil
from pathlib import Path
from typing import Union


def format_size(size_bytes: int) -> str:
    """Переводит байты в человекочитаемый формат (B, KB, MB)."""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def validate_sandbox_path(filepath: str | Path) -> Path:
    """
    Гейткипер песочницы: разрешает работу с файлами строго внутри папки sandbox/.
    Защищает от Path Traversal атак (выхода за пределы директории).
    """
    sandbox_dir = (Path.cwd() / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    path_str = str(filepath).replace("\\", "/")
    if path_str.startswith("sandbox/"):
        path_str = path_str[8:]

    resolved = (sandbox_dir / path_str).resolve()
    if not resolved.is_relative_to(sandbox_dir):
        raise PermissionError(
            "Доступ запрещен: можно работать с файлами только в пределах папки sandbox/"
        )

    return resolved


def parse_int_or_str(value: Union[int, str]) -> Union[int, str]:
    """Утилитный метод для преобразования строковых ID Telegram в числа."""
    try:
        return int(value)
    except ValueError:
        return str(value).strip()


def truncate_text(
    text: str, max_chars: int, suffix: str = "... [Вывод обрезан. Превышен лимит символов] ..."
) -> str:
    """Универсальная защита контекста от переполнения огромными текстами."""

    if len(text) > max_chars:
        return text[:max_chars] + f"\n{suffix}"
    return text


def get_project_root() -> Path:
    """Гарантированно возвращает абсолютный путь к корню проекта JAWL."""
    return Path(__file__).resolve().parent.parent.parent


def get_pid_file_path() -> Path:
    """Единый путь к PID-файлу для всех модулей."""
    return get_project_root() / "src" / "utils" / "local" / "data" / "agent.pid"


def is_agent_running() -> bool:
    """Проверяет, работает ли агент на самом деле (логика перенесена из screens)."""
    pid_file = get_pid_file_path()
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            # Проверяем, что это не какой-то левый процесс занял этот PID
            return proc.is_running() and "python" in proc.name().lower()
        return False
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        if pid_file.exists():
            try:
                pid_file.unlink()
            except:
                pass
        return False
