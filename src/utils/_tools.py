import psutil
from pathlib import Path
from typing import Union
import re
import html


def format_size(size_bytes: int) -> str:
    """Переводит байты в человекочитаемый формат (B, KB, MB, GB, TB, PB)."""

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
    text: str,
    max_chars: int,
    suffix: str = "\n... [Вывод обрезан. Превышен лимит символов]",
) -> str:
    """Универсальная защита контекста от переполнения огромными текстами."""

    if len(text) > max_chars:
        return text[:max_chars] + suffix
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
            except Exception:
                pass
        return False


def clean_html(raw_html: str) -> str:
    """
    Мощная и быстрая очистка текста от HTML-мусора.
    Вырезает скрипты, стили, комментарии, HTML-теги и декодирует сущности (&amp; -> &).
    """

    if not raw_html:
        return ""

    # 1. Удаляем скрипты и стили вместе с их содержимым (игнорируя регистр и переносы строк)
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL
    )

    # 2. Удаляем HTML комментарии
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)

    # 3. Удаляем все остальные теги
    text = re.sub(r"<[^>]+>", " ", text)

    # 4. Декодируем HTML-сущности (&quot;, &amp;, &#39;, &nbsp; и т.д.)
    text = html.unescape(text)

    # 5. Схлопываем множественные пробелы и переносы в один пробел для плотности контекста
    text = re.sub(r"\s+", " ", text).strip()

    return text


def draw_image_grid(image_path: str | Path, step: int = 100):
    """
    Накладывает высококонтрастную координатную сетку на изображение.
    Используется для мультимодального зрения агента.
    """
    
    from PIL import Image, ImageDraw

    with Image.open(image_path) as img:
        # Создаем прозрачный слой для сетки
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        width, height = img.size

        # Рисуем линии сетки
        for x in range(0, width, step):
            draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 80), width=1)
        for y in range(0, height, step):
            draw.line([(0, y), (width, y)], fill=(255, 0, 0, 80), width=1)

        # Рисуем координаты с белой подложкой для идеальной читаемости LLM
        for x in range(0, width, step):
            for y in range(0, height, step):
                text = f"{x},{y}"
                # Примерный расчет ширины текста (стандартный шрифт PIL ~ 6x10 px на символ)
                text_w = len(text) * 6
                text_h = 10

                # Рисуем белую полупрозрачную подложку
                draw.rectangle(
                    [x + 2, y + 2, x + 4 + text_w, y + 4 + text_h], fill=(255, 255, 255, 220)
                )
                # Рисуем сам текст красным цветом
                draw.text((x + 4, y + 2), text, fill=(255, 0, 0, 255))

        # Склеиваем слои и сохраняем
        combined = Image.alpha_composite(img.convert("RGBA"), overlay)
        combined.convert("RGB").save(image_path)
