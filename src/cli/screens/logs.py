import time
from pathlib import Path

from rich.panel import Panel
from rich.text import Text
from src.cli.widgets.ui import console, print_error, print_info, clear_screen

LOG_FILE = Path(__file__).resolve().parent.parent.parent.parent / "logs" / "system.log"

# Маппинг цветов для интерфейса (аналог LogColors из logger.py, но в формате rich)
PREFIX_COLORS = {
    "[Heartbeat]": "bright_magenta",
    "[ReAct]": "bright_cyan",
    "[Thoughts]": "magenta",
    "[Agent Action]": "bright_green",
    "[Agent Action Result]": "dim",  # gray
    "[Skills]": "dim",
    "[LLM]": "bright_blue",
    "[Host OS]": "green",
    "[Web]": "magenta",
    "[Telegram Telethon]": "cyan",
    "[Telegram Aiogram]": "blue",
    "[Meta]": "white",
    "[Multimodality]": "bright_yellow",
    "[SQL DB]": "yellow",
    "[Vector DB]": "yellow",
    "[EventBus]": "dim",
    "[System]": "bright_white",
}


def _colorize_log_line(line: str) -> Text:
    """
    Раскрашивает чистую текстовую строку лога на лету.
    Использует объект Text, чтобы избежать конфликтов с тегами rich (типа [Web]).
    """
    # Убираем перенос строки, так как console.print добавит свой
    clean_line = line.rstrip("\n")
    text = Text(clean_line)

    if " - ERROR - " in clean_line or " - CRITICAL - " in clean_line:
        text.stylize("bold red")
        return text

    if " - WARNING - " in clean_line:
        text.stylize("bold yellow")
        return text

    # Красим по префиксу
    for prefix, color in PREFIX_COLORS.items():
        if prefix in clean_line:
            text.stylize(color)
            return text

    return text


def logs_screen() -> None:
    """Экран потокового вывода логов в реальном времени."""
    if not LOG_FILE.exists():
        print_error(f"Файл логов не найден: {LOG_FILE.name}")
        print_info("Возможно, агент еще ни разу не запускался.")
        console.print("\n[dim]Нажмите Enter для возврата в меню...[/dim]")
        input()
        return

    clear_screen()
    console.print(
        Panel(
            "[bold green]Стриминг system.log в реальном времени[/bold green]\n"
            "[dim]Нажмите Ctrl+C для возврата в главное меню[/dim]",
            border_style="green",
        )
    )

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # Прыгаем в конец файла минус 2000 байт, чтобы показать немного предыстории
            f.seek(0, 2)
            file_size = f.tell()
            f.seek(max(0, file_size - 2000))

            # Читаем остаток файла до конца, чтобы выровнять курсор чтения
            f.readlines()

            # Бесконечный цикл чтения новых строк (tail -f)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # Выводим раскрашенную строку
                console.print(_colorize_log_line(line))

    except KeyboardInterrupt:
        # Юзер нажал Ctrl+C
        print_info("\nВыход из режима просмотра логов.")
        time.sleep(0.5)
        return
