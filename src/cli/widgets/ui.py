import os
import time
import psutil
import yaml
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import questionary

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
    status = {"is_running": False, "uptime": "00:00", "model": "unknown", "interval": 0}

    # Читаем конфигурацию
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                status["model"] = config.get("llm", {}).get("model_name", "unknown")
                status["interval"] = config.get("system", {}).get("heartbeat_interval", 0)
        except Exception:
            pass

    # Проверяем живой ли процесс и считаем аптайм
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                status["is_running"] = True

                # Считаем аптайм от времени создания процесса ядром ОС
                uptime_seconds = time.time() - process.create_time()
                hours, remainder = divmod(int(uptime_seconds), 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours > 0:
                    status["uptime"] = f"{hours}h {minutes}m {seconds}s"
                else:
                    status["uptime"] = f"{minutes}m {seconds}s"
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return status


def clear_screen() -> None:
    """Очистка консоли под любую ОС."""
    os.system("cls" if os.name == "nt" else "clear")


def draw_header(version: str = "v0.9.0") -> None:
    """Очищает экран и отрисовывает главный логотип JAWL со статусом агента."""
    clear_screen()

    status = _get_agent_status()

    # Собираем текст логотипа
    text = Text(LOGO, style="bold cyan", justify="center")
    text.append(f"Version: {version}\n\n", style="dim cyan")

    # Добавляем плашку статуса
    if status["is_running"]:
        text.append("● ONLINE", style="bold green")
        text.append(
            f"  |  Uptime: {status['uptime']}  |  LLM Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="bold white",
        )
    else:
        text.append("○ OFFLINE", style="bold red")
        text.append(
            f"  |  Model: {status['model']}  |  Heartbeat: {status['interval']}s",
            style="dim white",
        )

    panel = Panel(text, border_style="cyan")
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
