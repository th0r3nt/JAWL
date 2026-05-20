import os
from pathlib import Path
from typing import Union, Optional, IO
import re
import html

from src.utils.logger import main_logger


def format_size(size_bytes: int) -> str:
    """
    Конвертирует размер из байтов в человекочитаемый формат (B, KB, MB, GB, TB, PB).

    Args:
        size_bytes (int): Размер файла в байтах.

    Returns:
        str: Отформатированная строка с подходящей единицей измерения.
    """

    if size_bytes < 0:
        return f"-{format_size(-size_bytes)}"

    units = ("B", "KB", "MB", "GB", "TB", "PB")
    size = float(size_bytes)
    for unit in units[:-1]:
        if size < 1024:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


def validate_sandbox_path(filepath: str | Path) -> Path:
    """
    Гейткипер песочницы: разрешает работу с файлами строго внутри папки sandbox/.
    Защищает от Path Traversal атак (выхода за пределы директории через '../').

    Args:
        filepath (str | Path): Относительный или абсолютный путь, запрошенный агентом.

    Returns:
        Path: Физический, очищенный и разрешенный абсолютный путь.

    Raises:
        PermissionError: Если запрошенный путь пытается выйти за пределы sandbox/.
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
    """
    Утилитный метод для преобразования строковых ID (например, Telegram) в числа.
    Если строку невозможно конвертировать в int (например, это @username), возвращает очищенную строку.

    Args:
        value (Union[int, str]): Исходное значение ID.

    Returns:
        Union[int, str]: Числовой ID или строковый юзернейм.
    """

    try:
        return int(value)
    except ValueError:
        return str(value).strip()


def truncate_text(
    text: str,
    max_chars: int,
    suffix: str = "\n... [Вывод обрезан. Превышен лимит символов]",
) -> str:
    """
    Универсальная защита контекста агента от переполнения гигантскими текстами.

    Гарантирует, что длина результата не превышает ``max_chars`` (с учетом
    длины суффикса). Если ``max_chars`` меньше длины суффикса, суффикс тоже
    обрезается, чтобы вписаться в лимит.

    Args:
        text (str): Исходный длинный текст.
        max_chars (int): Максимально допустимое количество символов (жесткий потолок).
        suffix (str, optional): Строка, которая будет добавлена в конец при обрезке.

    Returns:
        str: Оригинальный или усеченный текст с суффиксом, длиной строго <= max_chars.
    """

    if max_chars <= 0:
        return ""

    if len(text) <= max_chars:
        return text

    if len(suffix) >= max_chars:
        return suffix[:max_chars]

    body_budget = max_chars - len(suffix)
    return text[:body_budget] + suffix


def get_project_root() -> Path:
    """
    Вычисляет и гарантированно возвращает абсолютный путь к корню проекта JAWL.

    Returns:
        Path: Абсолютный путь директории фреймворка.
    """

    return Path(__file__).resolve().parent.parent.parent


def get_pid_file_path() -> Path:
    """
    Возвращает единый путь к PID-файлу для всех модулей системы.

    Returns:
        Path: Путь к файлу agent.pid.
    """

    return get_project_root() / "src" / "utils" / "local" / "data" / "agent.pid"


def get_lock_file_path() -> Path:
    """
    Возвращает путь к файлу блокировки (Mutex) для защиты от двойного запуска.
    """

    return get_project_root() / "src" / "utils" / "local" / "data" / "agent.lock"


def clean_html(raw_html: str) -> str:
    """
    Выполняет мощную и быструю очистку текста от HTML-мусора для экономии токенов LLM.
    Вырезает <script>, <style>, комментарии, теги и декодирует HTML-сущности.

    Args:
        raw_html (str): Сырая строка с HTML-разметкой.

    Returns:
        str: Чистый текст, готовый для внедрения в промпт агента.
    """

    if not raw_html:
        return ""

    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL
    )
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def draw_image_grid(image_path: str | Path, step: int = 100) -> None:
    """
    Накладывает высококонтрастную полупрозрачную координатную сетку на изображение.
    Используется навыком take_screenshot для точного визуального позиционирования
    элементов мультимодальными моделями (Vision LLM).
    """

    from PIL import Image, ImageDraw

    with Image.open(image_path) as img:
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        width, height = img.size

        for x in range(0, width, step):
            draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 80), width=1)
        for y in range(0, height, step):
            draw.line([(0, y), (width, y)], fill=(255, 0, 0, 80), width=1)

        for x in range(0, width, step):
            for y in range(0, height, step):
                text = f"{x},{y}"
                text_w = len(text) * 6
                text_h = 10

                draw.rectangle(
                    [x + 2, y + 2, x + 4 + text_w, y + 4 + text_h], fill=(255, 255, 255, 220)
                )
                draw.text((x + 4, y + 2), text, fill=(255, 0, 0, 255))

        combined = Image.alpha_composite(img.convert("RGBA"), overlay)
        combined.convert("RGB").save(image_path)


def dump_prompt_to_file(filename: str, messages: list, meta_header: str = "") -> None:
    """
    Сохраняет контекст (prompts) в Markdown-файл для отладки.
    """
    try:
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            if meta_header:
                f.write(f"{meta_header}\n\n---\n\n")

            for m in messages:
                role = getattr(
                    m, "role", m.get("role", "unknown") if isinstance(m, dict) else "unknown"
                )
                content = getattr(
                    m, "content", m.get("content", "") if isinstance(m, dict) else ""
                )
                f.write(f"### Role: {role}\n{content}\n\n---\n")
    except Exception as e:
        main_logger.error(f"[System] Не удалось сохранить промпт в {filename}: {e}")


def get_python_module_docstring(filepath: Path, max_length: int = 150) -> str:
    """
    Извлекает module-level docstring из Python файла.
    """
    if filepath.suffix.lower() != ".py":
        return ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            head = f.read(2048)

        match = re.search(r"^\s*(?:#.*?\n\s*)*(['\"]{3})(.*?)\1", head, re.DOTALL)

        if match:
            doc = match.group(2)
            clean_doc = " ".join(doc.split())

            if len(clean_doc) > max_length:
                clean_doc = clean_doc[:max_length] + "..."

            return f' ["""{clean_doc}"""]'

        return ""
    except Exception:
        return ""


class SystemInstanceLock:
    """
    Эксклюзивная блокировка инстанса (Mutex) через отдельный lock-файл.
    Кроссплатформенная реализация: msvcrt (Windows) и fcntl (Unix).
    """

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self._file: Optional[IO] = None

    def acquire(self) -> bool:
        """Пытается эксклюзивно заблокировать файл. Возвращает True при успехе."""
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Открываем в a+, чтобы создать файл, если его нет, но читать/писать
            self._file = open(self.lock_file, "a+", encoding="utf-8")
            fd = self._file.fileno()

            if os.name == "nt":
                import msvcrt

                # Блокируем 1 байт с начала файла
                self._file.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Записываем наш PID для истории
            self._file.seek(0)
            self._file.truncate()
            self._file.write(str(os.getpid()))
            self._file.flush()
            return True

        except (IOError, OSError, PermissionError):
            if self._file:
                self._file.close()
                self._file = None
            return False

    def release(self) -> None:
        """Снимает блокировку и закрывает файл."""
        if self._file:
            try:
                fd = self._file.fileno()
                if os.name == "nt":
                    import msvcrt

                    self._file.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass

            try:
                self._file.close()
            except Exception:
                pass
            self._file = None


def is_agent_running() -> bool:
    """
    Проверяет, работает ли процесс агента на самом деле.
    Использует проверку File Lock ОС для 100% гарантии.

    Returns:
        bool: True, если агент запущен. False в противном случае.
    """

    lock_file = get_lock_file_path()
    pid_file = get_pid_file_path()

    is_locked = False
    try:
        # Пытаемся получить лок на файл-мьютекс
        with open(lock_file, "a+", encoding="utf-8") as f:
            fd = f.fileno()
            if os.name == "nt":
                import msvcrt

                f.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
    except (IOError, OSError, PermissionError):
        is_locked = True

    if is_locked:
        return True

    # Если лок свободен - агент "умер" (или не запускался). Чистим за собой мусор.
    try:
        pid_file.unlink(missing_ok=True)
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass

    return False
