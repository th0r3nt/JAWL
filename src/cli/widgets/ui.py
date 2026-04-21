import os
import time
import psutil
import yaml
from pathlib import Path

from src.utils._tools import get_pid_file_path

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
import questionary

from src.cli.screens.agent_control import _is_agent_running

console = Console()

LOGO = """
     ██╗  █████╗  ██╗    ██╗ ██╗
     ██║ ██╔══██╗ ██║    ██║ ██║
     ██║ ███████║ ██║ █╗ ██║ ██║
██   ██║ ██╔══██║ ██║███╗██║ ██║
╚█████╔╝ ██║  ██║ ╚███╔███╔╝ ███████╗
 ╚════╝  ╚═╝  ╚═╝  ╚══╝╚══╝  ╚══════╝
         Just A While Loop
"""

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PID_FILE = ROOT_DIR / "src" / "utils" / "local" / "data" / "agent.pid"
SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"


def _get_agent_status() -> dict:
    """Легковесно собирает статус агента (без IPC, напрямую из ОС и конфигов)."""

    is_running = _is_agent_running()

    status = {"is_running": is_running, "uptime": "00:00", "model": "unknown", "interval": 0}

    # Читаем конфигурацию
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                status["model"] = config.get("llm", {}).get("model_name", "unknown")
                status["interval"] = config.get("system", {}).get("heartbeat_interval", 0)
        except Exception:
            pass

    # Считаем аптайм, только если процесс реально жив
    if is_running:
        try:
            pid_file = get_pid_file_path()
            pid = int(pid_file.read_text().strip())
            process = psutil.Process(pid)

            uptime_seconds = time.time() - process.create_time()
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                status["uptime"] = f"{hours}h {minutes}m {seconds}s"
            else:
                status["uptime"] = f"{minutes}m {seconds}s"

        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
            # Если файл исчез или процесс умер прямо во время замера - не страшно
            status["is_running"] = False

    return status


def clear_screen() -> None:
    """Очистка консоли под любую ОС."""
    os.system("cls" if os.name == "nt" else "clear")


def draw_header(version: str = "v0.9.0") -> None:
    """Очищает экран и отрисовывает главный логотип JAWL со статусом агента."""
    clear_screen()

    status = _get_agent_status()

    # 1. Логотип (убираем лишние переносы по краям, чтобы не было дыр)
    logo_text = Text(LOGO.strip("\n"), style="bold cyan")

    # 2. Версия (добавляем \n в конце для отступа перед статусом)
    version_text = Text(f"{version}\n", style="dim cyan")

    # 3. Плашка статуса
    status_text = Text()
    if status["is_running"]:
        status_text.append("● ONLINE", style="bold green")
        status_text.append(
            f"  |  Uptime: {status['uptime']}  |  Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="bold white",
        )
    else:
        status_text.append("○ OFFLINE", style="bold red")
        status_text.append(
            f"  |  Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="dim white",
        )

    # Группируем и железобетонно выравниваем всё как независимые "коробки"
    content = Group(
        Align.center(logo_text), Align.center(version_text), Align.center(status_text)
    )

    panel = Panel(content, border_style="cyan")
    console.print(panel)


def print_success(msg: str) -> None:
    """Выводит сообщение об успехе."""
    console.print(f"[bold green]✓ {msg}[/bold green]")


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
