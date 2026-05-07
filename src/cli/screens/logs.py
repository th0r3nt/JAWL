import time
from pathlib import Path
from collections import deque
from rich.panel import Panel
from rich.text import Text
from src.cli.widgets.ui import console, print_error, print_info, clear_screen, set_window_title

LOG_DIR = Path("logs")

# Карта соответствия типов логов и имен файлов
LOG_FILES = {
    "main": "main.log",
    "agent": "agent.log",
    "swarm": "subagents.log",
    "tot": "tot.log",
    "subconscious": "subconscious.log",
}

# Маппинг цветов
PREFIX_COLORS = {
    "[Heartbeat]": "bright_magenta",
    "[ReAct]": "bright_cyan",
    "[Thoughts]": "magenta",
    "[Agent Action]": "bright_green",
    "[Agent Action Result]": "dim",
    "[LLM]": "bright_blue",
    "[Swarm]": "bright_yellow",
    "[Subagent ReAct]": "yellow",
    "[Tree of Thoughts]": "cyan",
    "[Subconscious]": "bright_magenta",
    "[System]": "bright_white",
}

_current_log_color = ""


def _colorize_log_line(line: str) -> Text:
    global _current_log_color
    clean_line = line.rstrip("\n")
    text = Text(clean_line)

    if " - ERROR - " in clean_line or " - CRITICAL - " in clean_line:
        _current_log_color = "bold red"
    elif " - WARNING - " in clean_line:
        _current_log_color = "bold yellow"
    else:
        for prefix, color in PREFIX_COLORS.items():
            if prefix in clean_line:
                _current_log_color = color
                break

    if _current_log_color:
        text.stylize(_current_log_color)
    return text


def logs_screen(log_type: str = "main") -> None:
    """
    Экран потокового вывода логов с защитой от FileLock на ОС Windows.
    Умеет на лету подхватывать файлы при их ротации (RotatingFileHandler).
    """

    file_name = LOG_FILES.get(log_type, "main.log")
    log_path = LOG_DIR / file_name

    set_window_title(f"JAWL Logs - {log_type.upper()}")

    if not log_path.exists():
        clear_screen()
        print_error(f"Файл логов '{file_name}' еще не создан.")
        print_info("Возможно, эта подсистема еще не запускалась.")
        console.print("\n[dim]Нажмите Enter для возврата.[/dim]")
        input()
        return

    clear_screen()
    console.print(
        Panel(
            f"[bold green]Стриминг: {file_name}[/bold green]\n"
            f"[dim]Тип: {log_type.upper()} | Ctrl+C для выхода[/dim]",
            border_style="green",
            expand=False,
        )
    )

    last_pos = 0
    curr_inode = -1

    try:
        # Первичное чтение хвоста лога для контекста
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = list(deque(f, maxlen=150))
                for line in lines:
                    console.print(_colorize_log_line(line))
                last_pos = f.tell()
                curr_inode = log_path.stat().st_ino
        except (PermissionError, FileNotFoundError):
            pass

        # Бесконечный цикл стриминга (без удержания файлового дескриптора)
        while True:
            time.sleep(0.2)
            if not log_path.exists():
                continue

            try:
                stat = log_path.stat()
                new_inode = stat.st_ino
                current_size = stat.st_size

                # Проверка на ротацию логером или ручную очистку юзером
                if new_inode != curr_inode or current_size < last_pos:
                    last_pos = 0
                    curr_inode = new_inode
                    console.print(
                        Panel(
                            "[dim yellow]Лог-файл был ротирован или очищен. Чтение нового потока.[/dim yellow]"
                        )
                    )

                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_pos)
                    new_data = f.read()
                    last_pos = f.tell()

                if new_data:
                    # Избегаем лишних пустых строк в консоли при сплите
                    if new_data.endswith("\n"):
                        new_data = new_data[:-1]

                    for line in new_data.split("\n"):
                        console.print(_colorize_log_line(line))

            except (PermissionError, FileNotFoundError):
                # Файл в данный момент заблокирован ротатором для переименования, просто ждем
                pass

    except KeyboardInterrupt:
        return
