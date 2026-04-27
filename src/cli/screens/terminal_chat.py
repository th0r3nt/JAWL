import asyncio
import json
from pathlib import Path

import questionary
from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.patch_stdout import patch_stdout
from rich.panel import Panel
from rich.markdown import Markdown

from src.cli.widgets.ui import (
    console,
    print_error,
    print_info,
    print_success,
    clear_screen,
    draw_header,
    get_custom_style,
    launch_in_new_window,
)
from src.utils.settings import load_config
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


async def _chat_loop(port: int, history_file: Path, agent_name: str):
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        # Секретное рукопожатие, чтобы спастись от сканеров портов (IDE Auto-Forwarding)
        writer.write(b"JAWL_HANDSHAKE\n")
        await writer.drain()

    except ConnectionRefusedError:
        print_error("Не удалось подключиться к чату.")
        print_info("Проверьте, что агент запущен и интерфейс 'Host Terminal' включен.")
        print("\nНажмите Enter для возврата...")
        input()
        return

    clear_screen()
    console.print(
        Panel(
            f"[bold cyan]Интерактивный чат с агентом {agent_name}[/bold cyan]\n"
            "[dim]Отправка: Enter[/dim]\n"
            "[dim]Выход: /exit или Ctrl+C[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    # Подгружаем историю диалога
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            for msg in history[-15:]:
                sender = msg.get("sender")
                text = msg.get("text", "")

                if sender == "User":
                    # Используем нативный форматер prompt_toolkit
                    print_formatted_text(HTML(f"<ansigreen><b>Вы:</b></ansigreen> {text}"))
                else:
                    print_formatted_text(
                        HTML(f"\n<ansimagenta><b>{sender}:</b></ansimagenta>")
                    )
                    console.print(Markdown(text))

            print_formatted_text(HTML("\n<style fg='gray'>--- Конец истории ---</style>\n"))
        except Exception:
            pass

    session = PromptSession()

    async def receive_messages():
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                raw_text = data.decode("utf-8").strip()
                if not raw_text:
                    continue

                try:
                    payload = json.loads(raw_text)
                    message_text = payload.get("text", "")
                except json.JSONDecodeError:
                    message_text = raw_text

                with patch_stdout():
                    print_formatted_text(
                        HTML(f"\n<ansimagenta><b>{agent_name}:</b></ansimagenta>")
                    )
                    console.print(Markdown(message_text))
                    print("")  # Пустая строка для "воздуха"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            with patch_stdout():
                # Заменяем конфликтующий rich на нативный HTML-форматтер prompt_toolkit
                print_formatted_text(
                    HTML(f"\n<ansired><b>✗ Связь разорвана:</b> {e}</ansired>")
                )
                print_formatted_text(
                    HTML(
                        "<style fg='gray'>Введите /exit или нажмите Ctrl+C для выхода.</style>\n"
                    )
                )

    receive_task = asyncio.create_task(receive_messages())

    try:
        while True:
            with patch_stdout():
                # Раскрашиваем строку ввода
                user_input = await session.prompt_async(
                    HTML("<ansigreen><b>Вы:</b></ansigreen> ")
                )

            text = user_input.strip()
            if not text:
                continue

            if text.lower() in ["/exit", "/quit"]:
                break

            writer.write((text + "\n").encode("utf-8"))
            await writer.drain()

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        receive_task.cancel()
        writer.close()
        await writer.wait_closed()


def terminal_chat_screen() -> None:
    """Главное подменю терминала."""
    style = get_custom_style()

    while True:
        draw_header()

        choice = questionary.select(
            "Чат с агентом:",
            choices=[
                questionary.Choice("💬 Открыть чат", "open"),
                questionary.Choice("🧹 Очистить историю чата", "clear_history"),
                questionary.Separator(" "),
                questionary.Choice("↩ Назад", "back"),
            ],
            style=style,
            qmark="",
            instruction="",
        ).ask()

        if choice == "back" or choice is None:
            break

        if choice == "open":
            launch_in_new_window("--terminal")  # Запускаем в новом окне
        elif choice == "clear_history":
            _clear_terminal_history()


def _open_terminal_chat() -> None:
    """Проверки и запуск самого терминала."""
    if not _is_agent_running():
        print_error(
            "Ошибка: Агент не запущен. Для общения с ним необходимо запустить основной код."
        )
        print("\nНажмите Enter для возврата.")
        input()
        return

    settings, interfaces = load_config()

    if not hasattr(interfaces.host, "terminal") or not interfaces.host.terminal.enabled:
        print_error("Интерфейс 'Host Terminal' отключен в настройках (interfaces.yaml).")
        print("\nНажмите Enter для возврата.")
        input()
        return

    base_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "host" / "terminal"
    )
    history_file = base_dir / "history.json"
    port_file = base_dir / "terminal.port"
    agent_name = settings.identity.agent_name

    if not port_file.exists():
        print_error("Сервер терминала еще не запущен/произошла ошибка.")
        print_info(" Убедитесь, что агент работает и инициализация завершена.")
        print("\nНажмите Enter для возврата.")
        input()
        return

    try:
        active_port = int(port_file.read_text().strip())
    except ValueError:
        print_error("Файл порта поврежден.")
        print("\nНажмите Enter для возврата.")
        input()
        return

    # Блокирующий вызов асинхронного чата с нужным портом
    asyncio.run(_chat_loop(active_port, history_file, agent_name))


def _clear_terminal_history() -> None:
    """Очистка файла истории терминала."""
    base_dir = (
        ROOT_DIR / "src" / "utils" / "local" / "data" / "interfaces" / "host" / "terminal"
    )
    history_file = base_dir / "history.json"

    if history_file.exists():
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False)
            print_success("История терминала успешно очищена.")
        except Exception as e:
            print_error(f"Не удалось очистить историю: {e}")
    else:
        print_info(" История уже пуста (файл не найден).")

    print("\nНажмите Enter для возврата.")
    input()
