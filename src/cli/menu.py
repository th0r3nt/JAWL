import sys
import time
import threading

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.formatted_text import ANSI, HTML

from src.cli.widgets.ui import (
    get_header_ansi,
    flush_input,
    launch_in_new_window,
    clear_screen,
    draw_header,
    print_info,
)

from src.cli.screens.agent_control import start_agent_screen, stop_agent_screen
from src.cli.screens.setup_wizard import setup_wizard_screen
from src.cli.screens.database_manager import database_manager_screen
from src.cli.screens.terminal_chat import terminal_chat_screen


def main_menu() -> None:
    """Главный бесконечный цикл меню с живым дашбордом."""

    choices = [
        ("🚀 Запустить агента", "start"),
        ("⏹️ Остановить агента", "stop"),
        ("💻 Чат", "terminal"),
        ("📋 Логи", "logs"),
        ("⚙️ Мастер настройки интерфейсов", "setup"),
        ("🗄️ Управление базами данных", "db_manager"),
        ("❌ Выход", "exit"),
    ]

    while True:
        clear_screen()
        flush_input()

        selected_index = 0
        result = None

        header_control = FormattedTextControl(ANSI(get_header_ansi()))

        def get_menu_text():
            lines = [
                " Добро пожаловать в JAWL. Выберите действие:",
                " (Используйте стрелочки ↑/↓ и Enter)\n",
            ]
            for i, (label, val) in enumerate(choices):
                if i == selected_index:
                    lines.append(f"<ansicyan><b> » {label}</b></ansicyan>")
                else:
                    lines.append(f"   {label}")
            return HTML("\n".join(lines))

        menu_control = FormattedTextControl(get_menu_text)

        layout = Layout(
            HSplit(
                [
                    Window(content=header_control, dont_extend_height=True),
                    Window(content=menu_control, dont_extend_height=True),
                ]
            )
        )

        bindings = KeyBindings()

        @bindings.add("up")
        @bindings.add("k")
        def move_up(event):
            nonlocal selected_index
            selected_index = max(0, selected_index - 1)
            menu_control.text = get_menu_text()

        @bindings.add("down")
        @bindings.add("j")
        def move_down(event):
            nonlocal selected_index
            selected_index = min(len(choices) - 1, selected_index + 1)
            menu_control.text = get_menu_text()

        @bindings.add("enter")
        def select_item(event):
            nonlocal result
            result = choices[selected_index][1]
            event.app.exit()

        @bindings.add("c-c")
        def quit_app(event):
            nonlocal result
            result = "exit"
            event.app.exit()

        app = Application(
            layout=layout,
            key_bindings=bindings,
            full_screen=False,
            erase_when_done=True,  # ВАЖНО: стираем UI после выбора, чтобы не мусорить в консоли
        )

        stop_thread = threading.Event()

        def live_update():
            # wait(1.0) заменяет time.sleep(1) и моментально прерывается при stop_thread.set()
            while not stop_thread.wait(1.0):
                if not stop_thread.is_set():
                    header_control.text = ANSI(get_header_ansi())
                    app.invalidate()

        updater_thread = threading.Thread(target=live_update, daemon=True)
        updater_thread.start()

        app.run()

        stop_thread.set()
        updater_thread.join(timeout=1.0)

        if result is None or result == "exit":
            draw_header()
            print_info(" Отключение. До встречи.")
            time.sleep(1)
            sys.exit(0)

        # Отрисовываем чистую статичную шапку (логотип + статус),
        # чтобы экранам запуска/остановки было где выводить свои логи.
        draw_header()

        # Маршрутизация
        if result == "start":
            start_agent_screen()
        elif result == "stop":
            stop_agent_screen()
        elif result == "terminal":
            terminal_chat_screen()
        elif result == "logs":
            launch_in_new_window("--logs")
        elif result == "setup":
            setup_wizard_screen()
        elif result == "db_manager":
            database_manager_screen()
