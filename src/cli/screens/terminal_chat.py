import asyncio
import json
import io
from pathlib import Path

import questionary
from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.cli.widgets.ui import (
    print_error,
    print_info,
    print_success,
    clear_screen,
    draw_header,
    get_custom_style,
    launch_in_new_window,
    set_window_title,
)
from src.utils.settings import load_config
from src.cli.screens.agent_control import _is_agent_running

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def _print_markdown_safe(text: str) -> None:
    """
    Рендерит Markdown в буфер, сохраняя цвета (ANSI), и безопасно выводит
    через prompt_toolkit. Решает проблему конфликта спецсимволов.
    """
    formatted_text = text.replace("\n", "  \n")

    # Рендерим rich в виртуальный буфер
    str_console = Console(file=io.StringIO(), force_terminal=True, color_system="standard")
    str_console.print(Markdown(formatted_text))
    ansi_str = str_console.file.getvalue()

    # Обрезаем лишний перенос строки от rich, чтобы не ломать верстку
    if ansi_str.endswith("\n"):
        ansi_str = ansi_str[:-1]

    print_formatted_text(ANSI(ansi_str))


async def _chat_loop(port: int, history_file: Path, agent_name: str) -> None:
    set_window_title(f"JAWL - Чат с агентом {agent_name}")

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"JAWL_HANDSHAKE\n")
        await writer.drain()

    except ConnectionRefusedError:
        print_error("Не удалось подключиться к чату.")
        print_info("Проверьте, что агент запущен и интерфейс 'Host Terminal' включен.")
        print("\nНажмите Enter для возврата...")
        input()
        return

    clear_screen()

    # Здесь используем обычный Console, так как мы еще не вошли в цикл ввода
    Console().print(
        Panel(
            f"[bold cyan]Интерактивный чат с агентом {agent_name}[/bold cyan]\n"
            "[dim]Отправка: Enter[/dim]\n"
            "[dim]Выход: /exit или Ctrl+C[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            for msg in history[-15:]:
                sender = msg.get("sender")
                text = msg.get("text", "")
                time_str = msg.get("time", "")

                time_prefix = f"<style fg='gray'>[{time_str}]</style> " if time_str else ""

                if sender == "User":
                    print_formatted_text(
                        HTML(f"{time_prefix}<ansigreen><b>Вы:</b></ansigreen> {text}")
                    )
                else:
                    print_formatted_text(
                        HTML(f"\n{time_prefix}<ansimagenta><b>{sender}:</b></ansimagenta>")
                    )
                    _print_markdown_safe(text)

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

                raw_text = data.decode("utf-8", errors="replace").strip()
                if not raw_text:
                    continue

                time_str = ""
                try:
                    payload = json.loads(raw_text)
                    message_text = payload.get("text", "")
                    time_str = payload.get("time", "")
                except json.JSONDecodeError:
                    message_text = raw_text

                time_prefix = f"<style fg='gray'>[{time_str}]</style> " if time_str else ""

                with patch_stdout():
                    print_formatted_text(
                        HTML(f"\n{time_prefix}<ansimagenta><b>{agent_name}:</b></ansimagenta>")
                    )
                    _print_markdown_safe(message_text)
                    print("")

        except asyncio.CancelledError:
            pass

        except Exception as e:
            with patch_stdout():
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
                user_input = await session.prompt_async(
                    HTML("<ansigreen><b>Вы:</b></ansigreen> ")
                )

            text = user_input.strip()

            try:
                text = text.encode("utf-8", errors="replace").decode("utf-8")
            except Exception:
                pass

            if not text:
                continue
            if text.lower() in ["/exit", "/quit"]:
                break

            payload = json.dumps({"text": text}, ensure_ascii=False)
            
            try:
                writer.write((payload + "\n").encode("utf-8"))
                await writer.drain()
            except (ConnectionError, OSError):
                with patch_stdout():
                    print_formatted_text(HTML("\n<ansired><b>✗ Соединение разорвано (Агент перезагружается или выключен).</b></ansired>"))
                break

    except (KeyboardInterrupt, EOFError):
        pass

    finally:
        receive_task.cancel()
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass # Игнорируем ошибки закрытия мертвого сокета


def terminal_chat_screen() -> None:
    set_window_title("JAWL - Терминал (Настройки)")
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
            instruction="\n (Стрелочки ↑/↓ для навигации)\n",
        ).ask()

        if choice == "back" or choice is None:
            break
        if choice == "open":
            launch_in_new_window("--terminal")
        elif choice == "clear_history":
            _clear_terminal_history()


def _open_terminal_chat() -> None:
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
        print("\nНажмите Enter для возврата.")
        input()
        return

    try:
        active_port = int(port_file.read_text().strip())
    except ValueError:
        print_error("Файл порта поврежден.")
        input()
        return

    asyncio.run(_chat_loop(active_port, history_file, agent_name))


def _clear_terminal_history() -> None:
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
