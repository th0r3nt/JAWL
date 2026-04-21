import time
from pathlib import Path

from rich.panel import Panel
from src.cli.widgets.ui import console, print_error, print_info, clear_screen

LOG_FILE = Path(__file__).resolve().parent.parent.parent.parent / "logs" / "system.log"


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
                # Выводим без добавления лишнего переноса строки, так как он есть в логе
                console.print(line, end="")

    except KeyboardInterrupt:
        # Юзер нажал Ctrl+C
        print_info("\nВыход из режима просмотра логов.")
        time.sleep(0.5)
        return
