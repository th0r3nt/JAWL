"""
Глобальные служебные инструменты и утилиты фреймворка JAWL.

Содержит функции для форматирования размеров, очистки HTML-контента, валидации
путей песочницы (Gatekeeper) и работы с процессами агента.
"""

import psutil
from pathlib import Path
from typing import Union
import re
import html


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

    # Корневой баг до этого фикса: text[:max_chars] + suffix могло быть длиннее
    # и самого max_chars, и исходного текста. "Защита" и увеличивала размер.
    if len(suffix) >= max_chars:
        # Суффикс сам по себе не влезает; обрезаем его, основной текст выкидываем.
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


def is_agent_running() -> bool:
    """
    Проверяет, работает ли процесс агента на самом деле.
    Исключает ложные срабатывания (когда PID-файл остался после краша системы).

    Returns:
        bool: True, если агент запущен и это процесс Python. False в противном случае.
    """

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
    Выполняет мощную и быструю очистку текста от HTML-мусора для экономии токенов LLM.
    Вырезает <script>, <style>, комментарии, теги и декодирует HTML-сущности.

    Args:
        raw_html (str): Сырая строка с HTML-разметкой.

    Returns:
        str: Чистый текст, готовый для внедрения в промпт агента.
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


def draw_image_grid(image_path: str | Path, step: int = 100) -> None:
    """
    Накладывает высококонтрастную полупрозрачную координатную сетку на изображение.
    Используется навыком take_screenshot для точного визуального позиционирования
    элементов мультимодальными моделями (Vision LLM).

    Args:
        image_path (str | Path): Путь к изображению, которое нужно модифицировать.
        step (int, optional): Шаг сетки в пикселях. По умолчанию 100.
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
