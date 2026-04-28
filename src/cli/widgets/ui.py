import os
import yaml
import sys
import platform
import subprocess
import io
import shutil
from pathlib import Path

from src.utils._tools import is_agent_running

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
import questionary

from src.__init__ import __version__

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
    """
    Легковесно собирает статус агента (без IPC, напрямую из ОС и конфигов).
    """

    status = {"is_running": is_agent_running(), "model": "unknown", "interval": 0}

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                status["model"] = config.get("llm", {}).get("model", "unknown")
                status["interval"] = config.get("system", {}).get("heartbeat_interval", 0)
        except Exception:
            pass

    return status


def _build_header_panel(version: str) -> Panel:
    """
    Собирает Rich Panel для шапки системы.
    """

    status = _get_agent_status()

    logo_text = Text(LOGO, style="bold cyan")
    subtitle_text = Text("Just A While Loop", style="bold cyan")
    version_text = Text(f"{version}\n", style="dim cyan")

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

    content = Group(
        Align.center(logo_text),
        Align.center(subtitle_text),
        Align.center(version_text),
        Align.center(status_text),
    )

    return Panel(content, border_style="cyan", expand=False)


def get_header_ansi(version: str = __version__) -> str:
    """
    Генерирует заголовок и возвращает его в виде ANSI строки (для prompt_toolkit).
    """

    panel = _build_header_panel(version)
    term_width = shutil.get_terminal_size().columns
    str_console = Console(file=io.StringIO(), force_terminal=True, width=term_width)
    str_console.print(panel)
    return str_console.file.getvalue()


def draw_header(version: str = __version__) -> None:
    """
    Очищает экран и отрисовывает главный логотип JAWL со статусом агента.
    """

    clear_screen()
    console.print(_build_header_panel(version))


def launch_in_new_window(arg: str) -> None:
    """
    Запускает jawl.py с определенным аргументом в новом окне ОС терминала.
    """

    script_path = ROOT_DIR / "jawl.py"
    cmd = [sys.executable, str(script_path), arg]
    system = platform.system()

    try:
        if system == "Windows":
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        elif system == "Darwin":
            cmd_str = f'"{sys.executable}" "{script_path}" {arg}'
            cmd_str_escaped = cmd_str.replace('"', '\\"')
            script = f'tell application "Terminal" to do script "{cmd_str_escaped}"'
            subprocess.Popen(["osascript", "-e", script])
        else:
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

                print_error(
                    "Не удалось найти графический терминал (вероятно, это сервер без GUI). Открытие в текущем окне."
                )
                import time
                time.sleep(1)
                # Используем блокирующий call вместо фонового Popen
                subprocess.call(cmd)

    except Exception as e:
        print_error(f"Ошибка при открытии нового окна: {e}")


def flush_input() -> None:
    """
    Кроссплатформенная очистка буфера ввода (stdin).
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


def print_success(msg: str) -> None:
    console.print(f"[bold green] ✓ {msg}[/bold green]")


def print_error(msg: str) -> None:
    console.print(f"[bold red]✗ {msg}[/bold red]")


def print_info(msg: str) -> None:
    console.print(f"[bold blue]ℹ {msg}[/bold blue]")


def wait_for_enter() -> None:
    console.print("\n[dim]Нажмите Enter для продолжения.[/dim]")
    input()


def get_custom_style() -> questionary.Style:
    return questionary.Style(
        [
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
        ]
    )
