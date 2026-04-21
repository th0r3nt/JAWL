"""
UI-виджеты для CLI.
Инкапсулирует работу с rich для переиспользования по всему CLI.
"""

import os
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


def clear_screen() -> None:
    """Очистка консоли под любую ОС."""
    os.system("cls" if os.name == "nt" else "clear")


def draw_header(version: str = "v0.9.0") -> None:
    """Очищает экран и отрисовывает главный логотип JAWL в рамке."""
    clear_screen()
    text = Text(LOGO, style="bold cyan", justify="center")
    panel = Panel(text, title="SYSTEM", subtitle=version, border_style="cyan")
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
