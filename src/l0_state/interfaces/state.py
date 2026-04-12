from typing import Literal

# Сюда складывают текущее состояние (входящие сообщения, метрики и прочее) все интерфейсы, которые работают
# Важно: этот файл является строго пассивным хранилищем: сам он ничего не делает, а лишь хранить данные для агента

# interfaces/state.py - это приборная панель агента.
# Когда агент просыпается (начинается тик), он не должен делать дорогие API-вызовы просто чтобы узнать, что кто-то ему написал.
# Он должен просто кинуть взгляд на приборную панель (L0).

# =======================================
# TELETHON
# =======================================


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

    def __init__(self, number_of_last_chats: int = 10):
        self.is_online = False

        self.number_of_last_chats = number_of_last_chats  # Количество хранимых последних чатов

        # Хранилище последних чатов
        self.last_chats = ""
        # Например:
        # User | ID: 192837465 | Название: th0r3nt [Непрочитанных: 1]
        # Group | ID: -10099887766 | Название: Python Backend Devs
        # Channel | ID: -10011223344 | Название: Хабр: IT Новости


# =======================================
# AIOGRAM
# =======================================


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
        self._chats_cache: dict[int, str] = {}  # Внутренний кэш: {chat_id: "строка форматирования"}


# =======================================
# Host OS
# =======================================


class HostOSState:
    """
    Хранит состояние Host OS.
    Телеметрия, время, аптайм.
    Обновляется слушателями (os/events.py) в фоне.
    """

    def __init__(self) -> None:
        self.is_online = False

        self.datetime = ""  # Время
        self.uptime = ""  # Аптайм хост-пк
        self.telemetry = ""  # CPU, ОЗУ, процессы
        self.sandbox_files = ""  # Текущие файлы в Sandbox
