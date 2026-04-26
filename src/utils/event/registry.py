from pydantic import BaseModel
from enum import Enum

# ============================================
# LEVEL
# ============================================


class EventLevel(int, Enum):
    CRITICAL = 50
    HIGH = 40
    MEDIUM = 30
    LOW = 20
    BACKGROUND = 10
    INFO = 0


# ============================================
# МОДЕЛЬ ОДНОГО СОБЫТИЯ
# ============================================


class EventConfig(BaseModel):
    name: str
    description: str
    level: EventLevel
    requires_attention: bool = True

    def __str__(self):
        return self.name


class Events:
    """
    Глобальный реестр всех доступных событий в системе JAWL.
    Определяет уровни важности для корректной работы Heartbeat-акселератора.
    """

    # ============================================
    # Telegram User API / Kurigram
    # ============================================

    KURIGRAM_MESSAGE_INCOMING = EventConfig(
        name="KURIGRAM_MESSAGE_INCOMING",
        description="Входящее сообщение в Telegram через User API / Kurigram.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    KURIGRAM_GROUP_MENTION = EventConfig(
        name="KURIGRAM_GROUP_MENTION",
        description="Упоминание в Telegram через User API / Kurigram.",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    KURIGRAM_MESSAGE_REACTION = EventConfig(
        name="KURIGRAM_MESSAGE_REACTION",
        description=(
            "Входящая эмодзи-реакция на сообщение в Telegram через User API / Kurigram."
        ),
        level=EventLevel.LOW,
        requires_attention=False,
    )

    KURIGRAM_CHANNEL_MESSAGE = EventConfig(
        name="KURIGRAM_CHANNEL_MESSAGE",
        description="Обычное сообщение в канале Telegram через User API / Kurigram.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    KURIGRAM_CHAT_ACTION = EventConfig(
        name="KURIGRAM_CHAT_ACTION",
        description=(
            "Системное действие в Telegram-чате через User API / Kurigram "
            "(вход/выход юзера, смена названия, закреп и т.д.)."
        ),
        level=EventLevel.LOW,
        requires_attention=False,
    )

    KURIGRAM_GROUP_MESSAGE = EventConfig(
        name="KURIGRAM_GROUP_MESSAGE",
        description="Обычное сообщение в Telegram-чате через User API / Kurigram.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # Telegram Aiogram
    # ============================================

    AIOGRAM_MESSAGE_INCOMING = EventConfig(
        name="AIOGRAM_MESSAGE_INCOMING",
        description="Входящее сообщение боту (Aiogram).",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    AIOGRAM_GROUP_MENTION = EventConfig(
        name="AIOGRAM_GROUP_MENTION",
        description="Упоминание бота в группе (Aiogram).",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    AIOGRAM_CHAT_ACTION = EventConfig(
        name="AIOGRAM_CHAT_ACTION",
        description="Системное действие в чате бота (вход/выход юзера, смена названия, закреп).",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    AIOGRAM_GROUP_MESSAGE = EventConfig(
        name="AIOGRAM_GROUP_MESSAGE",
        description="Обычное сообщение в группе, где есть бот.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # Host OS
    # ============================================

    HOST_OS_FILE_CREATED = EventConfig(
        name="OS_FILE_CREATED",
        description="В песочнице (sandbox) появился новый файл.",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    HOST_OS_FILE_MODIFIED = EventConfig(
        name="OS_FILE_MODIFIED",
        description="Файл в песочнице был изменен.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    HOST_OS_FILE_DELETED = EventConfig(
        name="HOST_OS_FILE_DELETED",
        description="Файл в песочнице был удален.",
        level=EventLevel.LOW,  # Фоновое уведомление
        requires_attention=False,
    )

    # ============================================
    # Email
    # ============================================

    EMAIL_INCOMING = EventConfig(
        name="EMAIL_INCOMING",
        description="Входящее электронное письмо.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # GITHUB
    # ============================================

    GITHUB_REPO_ACTIVITY = EventConfig(
        name="GITHUB_REPO_ACTIVITY",
        description="Активность в отслеживаемом GitHub репозитории (коммит, issue, PR).",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    # ============================================
    # Общие системные события
    # ============================================

    SYSTEM_CORE_START = EventConfig(
        name="SYSTEM_CORE_START",
        description="Запуск всей системы.",
        level=EventLevel.CRITICAL,
        requires_attention=True,
    )

    SYSTEM_CORE_STOP = EventConfig(
        name="SYSTEM_CORE_STOP",
        description="Отключение всей системы.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    SYSTEM_CALENDAR_ALARM = EventConfig(
        name="SYSTEM_CALENDAR_ALARM",
        description="Сработал таймер или регулярная задача из календаря.",  # TODO: в коде вообще используется поле description?
        level=EventLevel.HIGH,
        requires_attention=True,  # TODO: это вообще влияет на что-нибудь?
    )

    SYSTEM_CONFIG_UPDATED = EventConfig(
        name="SYSTEM_CONFIG_UPDATED",
        description="Обновление конфигурации системы через Meta-интерфейс.",
        level=EventLevel.INFO,
        requires_attention=False,
    )

    SYSTEM_SHUTDOWN_REQUESTED = EventConfig(
        name="SYSTEM_SHUTDOWN_REQUESTED",
        description="Агент запросил полное выключение системы.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    SYSTEM_REBOOT_REQUESTED = EventConfig(
        name="SYSTEM_REBOOT_REQUESTED",
        description="Агент запросил перезагрузку системы.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    @classmethod
    def all(cls) -> list[EventConfig]:
        events = []
        seen_names = set()
        for attr_value in vars(cls).values():
            if isinstance(attr_value, EventConfig) and attr_value.name not in seen_names:
                events.append(attr_value)
                seen_names.add(attr_value.name)
        return events


ALL_EVENTS = Events.all()
