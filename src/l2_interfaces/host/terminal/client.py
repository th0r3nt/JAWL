"""
Локальный TCP-сервер терминала (CLI-интерфейс пользователя).

Обеспечивает двунаправленную связь между интерфейсом командной строки (UI)
и шиной событий (EventBus) агента. Защищен механизмом Handshake,
игнорирующим порт-сканеры ОС и IDE (которые любят стучаться во все открытые сокеты).
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import system_logger
from src.utils.dtime import get_now_formatted
from src.utils.settings import HostTerminalConfig
from src.l2_interfaces.host.terminal.state import HostTerminalState


class HostTerminalClient:
    """
    TCP-сервер локального терминала.
    Управляет подключениями CLI-чата и передачей сообщений.
    """

    def __init__(
        self,
        state: HostTerminalState,
        config: HostTerminalConfig,
        data_dir: Path,
        agent_name: str,
        timezone: int,
    ) -> None:
        """
        Инициализирует TCP-сервер терминала.

        Args:
            state: L0 стейт терминала.
            config: Конфигурация.
            data_dir: Корневая директория локальных данных JAWL.
            agent_name: Имя агента для отображения в UI.
            timezone: Смещение часового пояса.
        """
        self.state = state
        self.config = config
        self.agent_name = agent_name
        self.timezone = timezone

        self.host = "127.0.0.1"
        self.port = 0  # 0 означает, что ОС выдаст любой свободный порт сама

        # Файлы стейта интерфейса
        self.history_file = data_dir / "interfaces" / "host" / "terminal" / "history.json"
        self.port_file = (
            data_dir / "interfaces" / "host" / "terminal" / "terminal.port"
        )  # Файл для порта

        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        self.server: Optional[asyncio.AbstractServer] = None
        self.active_writers: set[asyncio.StreamWriter] = set()

        # Очередь для передачи входящих сообщений/сигналов в events.py
        # Формат: (action_type, payload)
        self.incoming_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def start(self) -> None:
        """Запускает TCP сервер и сохраняет выданный ОС порт в файл для UI."""
        self._load_history()

        # ОС сама выдаст свободный порт
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)

        # Достаем реальный номер выданного порта
        actual_port = self.server.sockets[0].getsockname()[1]

        # Сохраняем его в файл, чтобы CLI знал, куда стучаться
        self.port_file.write_text(str(actual_port))
        self.state.is_online = True

        system_logger.info(f"[Host OS] Терминал-сервер запущен ({self.host}:{actual_port})")

    async def stop(self) -> None:
        """Штатно закрывает все активные сокеты."""
        self.state.is_online = False

        # Удаляем файл порта за ненадобностью
        if self.port_file.exists():
            try:
                self.port_file.unlink()
            except Exception:
                pass

        for writer in list(self.active_writers):
            writer.close()
            await writer.wait_closed()

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        system_logger.info("[Host OS] Терминал-сервер остановлен.")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """
        Корутина обработки нового TCP-соединения.
        Ожидает пароль 'JAWL_HANDSHAKE' (защита от мусорного трафика) и транслирует
        входящие текстовые потоки в очередь для обработки модулем Events.
        """

        try:
            # Ждем пароль-рукопожатие максимум 2 секунды
            handshake = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if handshake.decode("utf-8").strip() != "JAWL_HANDSHAKE":
                writer.close()
                await writer.wait_closed()
                return
        except (asyncio.TimeoutError, Exception):
            # Если подключился порт-сканер и молчит - сбрасываем
            writer.close()
            return

        # Если пароль верный - пускаем
        self.active_writers.add(writer)

        if not self.state.is_ui_connected:
            self.state.is_ui_connected = True
            system_logger.info("[Host OS] CLI-чат подключен к терминалу.")
            await self.incoming_queue.put(("_CONNECTION_OPENED", ""))

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break  # Отключился

                text = data.decode("utf-8").strip()
                if text:
                    # Извлекаем JSON payload
                    try:
                        parsed = json.loads(text)
                        msg_text = parsed.get("text", text)
                    except json.JSONDecodeError:
                        msg_text = text

                    if msg_text:
                        time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")
                        self._record_message("User", msg_text, time_str)
                        await self.incoming_queue.put(("_MESSAGE", msg_text))

        except asyncio.CancelledError:
            pass

        except Exception as e:
            system_logger.warning(f"[Host OS] Ошибка соединения терминала: {e}")

        finally:
            self.active_writers.discard(writer)

            # Проверяем, не осталось ли еще активных сессий
            if not self.active_writers and self.state.is_ui_connected:
                self.state.is_ui_connected = False
                system_logger.info("[Host OS] CLI-чат отключен от терминала.")
                await self.incoming_queue.put(("_CONNECTION_CLOSED", ""))

            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def broadcast_message(self, text: str) -> None:
        """
        Асинхронная рассылка сообщения от агента во все активные TCP-сессии (открытые консоли).
        Пакует текст в JSON с отметкой времени для парсинга на стороне CLI-виджетов.

        Args:
            text: Текст сообщения агента (поддерживает Markdown).
        """

        time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")
        self._record_message(self.agent_name, text, time_str)

        if not self.active_writers:
            return

        # Пакуем в JSON вместе со временем для красивого вывода в CLI
        payload = json.dumps({"text": text, "time": time_str}, ensure_ascii=False) + "\n"
        data = payload.encode("utf-8")

        for writer in list(self.active_writers):
            try:
                writer.write(data)
                await writer.drain()
            except Exception:
                self.active_writers.discard(writer)

    def _record_message(self, sender: str, text: str, time_str: str = "") -> None:
        """Пишет сообщение в L0 State и физический файл истории."""
        if not time_str:
            time_str = get_now_formatted(self.timezone, "%Y-%m-%d %H:%M:%S")

        self.state.add_message(sender, text, time_str)

        history = self._read_history_file()
        history.append({"time": time_str, "sender": sender, "text": text})

        if len(history) > self.config.history_limit:
            history = history[-self.config.history_limit :]

        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

    def _read_history_file(self) -> list:
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _load_history(self) -> None:
        """
        Подтягивает историю контекста из файла при рестарте сервера.
        """
        history = self._read_history_file()
        recent = history[-self.config.context_limit :]
        for msg in recent:
            self.state.add_message(msg["sender"], msg["text"], msg.get("time", ""))

    async def get_context_block(self, **kwargs: Any) -> str:
        if not self.state.is_online:
            return "### HOST TERMINAL [OFF]\nИнтерфейс отключен."

        ui_status = (
            "Окно терминала открыто."
            if self.state.is_ui_connected
            else "Окно терминала закрыто."
        )
        return f"### HOST TERMINAL [ON]\nСтатус: {ui_status}\n\nПоследние сообщения:\n{self.state.formatted_messages}"
