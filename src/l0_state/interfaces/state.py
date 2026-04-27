from typing import Literal

# Сюда складывают текущее состояние (входящие сообщения, метрики и прочее) все интерфейсы, которые работают
# Важно: этот файл является строго пассивным хранилищем: сам он ничего не делает, а лишь хранить данные для агента

# interfaces/state.py - это приборная панель агента.
# Когда агент просыпается (начинается тик), он не должен делать дорогие API-вызовы просто чтобы узнать, что кто-то ему написал.
# Он должен просто кинуть взгляд на приборную панель (L0).

# ==================================================================
# TELETHON
# ==================================================================


class TelethonChat:
    id: int  # ID чата
    chat_type: Literal["private", "group", "channel"]  # Тип чата
    name: str  # Название чата
    is_unread: bool  # Есть ли непрочитанные?


class TelethonState:
    """
    Хранит состояние Telethon-клиента.
    Последние n диалогов, статус непрочитанных.
    Обновляется слушателями (telethon/events.py) в фоне.
    """

    def __init__(self, number_of_last_chats: int = 15, private_chat_history_limit: int = 3):
        self.is_online = False

        self.number_of_last_chats = number_of_last_chats  # Количество хранимых последних чатов

        self.private_chat_history_limit = private_chat_history_limit

        # Хранилище последних чатов
        self.last_chats = ""
        # Например:
        # User | ID: 192837465 | Название: th0r3nt [Непрочитанных: 1]
        # Group | ID: -10099887766 | Название: Python Backend Devs
        # Channel | ID: -10011223344 | Название: Хабр: IT Новости

        self.account_info = "Данные профиля загружаются..."


# ==================================================================
# AIOGRAM
# ==================================================================


class AiogramState:
    """
    Хранит состояние Aiogram-клиента.
    Т.к. боты не могут запрашивать список всех чатов,
    мы храним N последних чатов, откуда приходили сообщения.
    """

    def __init__(self, number_of_last_chats: int = 10):
        self.is_online = False

        self.number_of_last_chats = number_of_last_chats

        self.last_chats = "Список диалогов пуст."
        self._chats_cache: dict[int, str] = (
            {}
        )  # Внутренний кэш: {chat_id: "строка форматирования"}


# ==================================================================
# Github
# ==================================================================


class GithubState:
    """
    Хранит состояние Github-клиента.
    Флаг is_online, информация об аккаунте агента, его репозиториях,
    уведомлениях и короткая история запросов.
    """

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

        self.account_info = "Ожидание инициализации..."
        self.own_repos = "Репозитории неизвестны."
        self.unread_notifications = "Уведомлений нет."

        # Watchers: { "owner/repo": "last_event_id" }
        self.tracked_repos: dict[str, str] = {}

        # MRU-кэш последних событий для вывода в контекст агента
        self.recent_watcher_events: list[str] = []

    def add_history(self, entry: str) -> None:
        """Добавляет запись в начало истории (самые свежие сверху)."""
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    def add_watcher_event(self, event_str: str) -> None:
        """Добавляет событие репозитория в контекст."""
        self.recent_watcher_events.insert(0, event_str)
        if len(self.recent_watcher_events) > 10:  # Храним последние 10 событий
            self.recent_watcher_events.pop()

    @property
    def github_history(self) -> str:
        if not self.history:
            return "История пуста."
        return "\n".join(f"- {item}" for item in self.history)


# ==================================================================
# EMAIL
# ==================================================================


class EmailState:
    """
    Хранит состояние Email-клиента.
    Отображает информацию об аккаунте и список последних писем в ящике.
    """

    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.recent_limit = recent_limit

        self.account_info = "Ожидание инициализации..."
        self.mailbox_preview = "Писем нет."


# ==================================================================
# Host OS
# ==================================================================


class HostOSState:
    """
    Хранит состояние Host OS.
    Телеметрия, время, аптайм.
    Обновляется слушателями (os/events.py) в фоне.
    """

    def __init__(self) -> None:
        self.is_online = False

        # Статические данные (определяются 1 раз при старте)
        self.os_info = ""  # Окно/Linux/Mac
        self.cpu_name = ""
        self.total_ram_gb = 0.0

        # Динамические данные
        self.datetime = ""  # Время
        self.uptime = ""  # Аптайм хост-пк
        self.telemetry = ""  # CPU, ОЗУ, процессы
        self.sandbox_files = ""  # Текущие файлы в Sandbox
        self.framework_files = ""  # Дерево директории JAWL
        self.active_daemons = "Нет запущенных демонов."

        self.polling_interval = ""

        self.opened_workspace_files: set[str] = set()  # Файлы, открытые в "редакторе" агента
        self.recent_file_changes: list[str] = (
            []
        )  # Кэш последних diff-ов (чтобы агент помнил, что менял)


# ==================================================================
# Host Terminal
# ==================================================================


class HostTerminalState:
    """
    Хранит состояние локального терминала и историю последних сообщений.
    """

    def __init__(self, context_limit: int = 15):
        self.is_online = False
        self.is_ui_connected = False
        self.context_limit = context_limit

        # Храним список строк для удобства сдвига (MRU)
        self.recent_messages: list[str] = []

    def add_message(self, sender: str, text: str, time_str: str = ""):
        """Добавляет сообщение в конец и сдвигает кэш, если превышен лимит."""
        prefix = f"[{time_str}] " if time_str else ""
        self.recent_messages.append(f"{prefix}[{sender}]: {text}")
        if len(self.recent_messages) > self.context_limit:
            self.recent_messages.pop(0)

    @property
    def formatted_messages(self) -> str:
        if not self.recent_messages:
            return "История сообщений пуста."
        return "\n".join(self.recent_messages)


# ==================================================================
# Web
# ==================================================================


class WebSearchState:
    """
    Хранит состояние веб-клиента (история браузера агента).
    Позволяет агенту помнить, что он недавно искал или читал.
    """

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

    def add_history(self, entry: str):
        """Добавляет запись в начало истории (самые свежие сверху)."""
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    @property
    def browser_history(self) -> str:
        if not self.history:
            return "История пуста."
        return "\n".join(f"- {item}" for item in self.history)


# ==================================================================
# Calendar
# ==================================================================


class CalendarState:
    """
    Хранит состояние календаря агента.
    Отображает ближайшие запланированные события.
    """

    def __init__(self):
        self.is_online = False
        self.upcoming_events = "Событий нет."
