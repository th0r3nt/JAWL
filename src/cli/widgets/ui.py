import os
import yaml
import sys
import platform
import subprocess
from pathlib import Path

from src.utils._tools import is_agent_running

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
import questionary

console = Console()

LOGO = "\n".join(
    [
        "     ██╗  █████╗  ██╗    ██╗ ██╗",
        "     ██║ ██╔══██╗ ██║    ██║ ██║",
        "     ██║ ███████║ ██║ █╗ ██║ ██║",
        "██   ██║ ██╔══██║ ██║███╗██║ ██║",
        "╚█████╔╝ ██║  ██║ ╚███╔███╔╝ ███████╗",
        " ╚════╝  ╚═╝  ╚═╝  ╚══╝╚══╝  ╚══════╝",
    ]
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.pid"
SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"


def _get_agent_status() -> dict:
    """Легковесно собирает статус агента (без IPC, напрямую из ОС и конфигов)."""

    # Убрали сбор аптайма, так как статичное меню не обновляет время.
    # is_agent_running() уже сам проверяет наличие и живость процесса через psutil
    status = {"is_running": is_agent_running(), "model": "unknown", "interval": 0}

    # Читаем конфигурацию
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                status["model"] = config.get("llm", {}).get("model", "unknown")
                status["interval"] = config.get("system", {}).get("heartbeat_interval", 0)
        except Exception:
            pass

    return status


def launch_in_new_window(arg: str) -> None:
    """Запускает jawl.py с определенным аргументом в новом окне ОС терминала."""
    script_path = ROOT_DIR / "jawl.py"

    # sys.executable указывает на Python внутри нашего venv
    cmd = [sys.executable, str(script_path), arg]

    system = platform.system()

    try:
        if system == "Windows":
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        elif system == "Darwin":
            # macOS AppleScript
            cmd_str = f'"{sys.executable}" "{script_path}" {arg}'
            cmd_str_escaped = cmd_str.replace('"', '\\"')
            script = f'tell application "Terminal" to do script "{cmd_str_escaped}"'
            subprocess.Popen(["osascript", "-e", script])
        else:
            # Linux (пытаемся найти популярный терминал)
            import shutil

            terminals = [
                ("gnome-terminal", ["--"]),
                ("konsole", ["-e"]),
                ("xfce4-terminal", ["-e"]),
                ("alacritty", ["-e"]),
                ("xterm", ["-e"]),
            ]
            for term, args in terminals:
                if shutil.which(term):
                    subprocess.Popen([term] + args + cmd)
                    return

            # Fallback если ничего не нашли
            print_error(
                "Не удалось найти терминал для открытия нового окна. Запускаем в текущем..."
            )
            subprocess.Popen(cmd)

    except Exception as e:
        print_error(f"Ошибка при открытии нового окна: {e}")


def flush_input() -> None:
    """
    Кроссплатформенная очистка буфера ввода (stdin).
    Удаляет все случайные нажатия клавиш, которые накопились, пока CLI был занят.
    """
    try:
        if os.name == "nt":
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getch()
        else:
            import termios

            termios.tcflush(sys.stdin, termios.TCIOFLUSH)
    except Exception:
        pass


def clear_screen() -> None:
    """Очистка консоли под любую ОС."""
    os.system("cls" if os.name == "nt" else "clear")


def draw_header(version: str = "v0.9.0") -> None:
    """Очищает экран и отрисовывает главный логотип JAWL со статусом агента."""
    clear_screen()

    status = _get_agent_status()

    # 1. Логотип (чистый арт без лишних отступов)
    logo_text = Text(LOGO, style="bold cyan")

    # 2. Подзаголовок вынесен отдельно для идеального математического центрирования
    subtitle_text = Text("Just A While Loop", style="bold cyan")

    # 3. Версия (добавляем \n в конце для отступа перед статусом)
    version_text = Text(f"{version}\n", style="dim cyan")

    # 4. Плашка статуса
    status_text = Text()
    if status["is_running"]:
        status_text.append("● ONLINE", style="bold green")
        status_text.append(
            f"  |  Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="bold white",
        )
    else:
        status_text.append("○ OFFLINE", style="bold red")
        status_text.append(
            f"  |  Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="dim white",
        )

    # Группируем и выравниваем каждый элемент НЕЗАВИСИМО друг от друга
    content = Group(
        Align.center(logo_text),
        Align.center(subtitle_text),
        Align.center(version_text),
        Align.center(status_text),
    )

    panel = Panel(content, border_style="cyan")
    console.print(panel)


def print_success(msg: str) -> None:
    """Выводит сообщение об успехе."""
    console.print(f"[bold green] ✓ {msg}[/bold green]")


def print_error(msg: str) -> None:
    """Выводит сообщение об ошибке."""
    console.print(f"[bold red]✗ {msg}[/bold red]")


def print_info(msg: str) -> None:
    """Выводит информационное сообщение."""
    console.print(f"[bold blue]ℹ {msg}[/bold blue]")


def wait_for_enter() -> None:
    """Ставит CLI на паузу, ожидая нажатия Enter от пользователя."""
    console.print("\n[dim]Нажмите Enter для продолжения.[/dim]")
    input()


def get_custom_style() -> questionary.Style:
    """Возвращает единый стиль для всех меню Questionary."""
    return questionary.Style(
        [
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
        ]
    )
