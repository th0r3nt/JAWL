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
# EVENT CONFIG MODEL
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
    Global system events directory.
    Defines event priority levels for the Heartbeat sleep accelerator.
    """

    # ============================================
    # Telegram Telethon
    # ============================================

    TELETHON_MESSAGE_INCOMING = EventConfig(
        name="TELETHON_MESSAGE_INCOMING",
        description="Incoming private/DM message.",
        level=EventLevel.CRITICAL,
        requires_attention=True,
    )

    TELETHON_GROUP_MENTION = EventConfig(
        name="TELETHON_GROUP_MENTION",
        description="Mention or group notification.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    TELETHON_MESSAGE_REACTION = EventConfig(
        name="TELETHON_MESSAGE_REACTION",
        description="Emoji reaction on message.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    TELETHON_CHANNEL_MESSAGE = EventConfig(
        name="TELETHON_CHANNEL_MESSAGE",
        description="Incoming channel post.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    TELETHON_CHAT_ACTION = EventConfig(
        name="TELETHON_CHAT_ACTION",
        description="System chat action event.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    TELETHON_GROUP_MESSAGE = EventConfig(
        name="TELETHON_GROUP_MESSAGE",
        description="Background group/thread message.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # Telegram Aiogram
    # ============================================

    AIOGRAM_MESSAGE_INCOMING = EventConfig(
        name="AIOGRAM_MESSAGE_INCOMING",
        description="Incoming message to bot (Aiogram).",
        level=EventLevel.CRITICAL,
        requires_attention=True,
    )

    AIOGRAM_GROUP_MENTION = EventConfig(
        name="AIOGRAM_GROUP_MENTION",
        description="Group mention of the bot (Aiogram).",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    AIOGRAM_CHAT_ACTION = EventConfig(
        name="AIOGRAM_CHAT_ACTION",
        description="System action in bot chat (join/leave, name change, pin).",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    AIOGRAM_GROUP_MESSAGE = EventConfig(
        name="AIOGRAM_GROUP_MESSAGE",
        description="Regular message in group where bot is present.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # Host OS
    # ============================================

    HOST_OS_FILE_CREATED = EventConfig(
        name="OS_FILE_CREATED",
        description="New file appeared in sandbox directory.",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    HOST_OS_FILE_MODIFIED = EventConfig(
        name="OS_FILE_MODIFIED",
        description="File within sandbox modified.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    HOST_OS_FILE_DELETED = EventConfig(
        name="HOST_OS_FILE_DELETED",
        description="File within sandbox deleted.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    HOST_OS_SANDBOX_EVENT = EventConfig(
        name="HOST_OS_SANDBOX_EVENT",
        description="Event signal from sandbox daemon/script.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # WEB HOOKS
    # ============================================

    WEBHOOK_MESSAGE_INCOMING = EventConfig(
        name="WEBHOOK_MESSAGE_INCOMING",
        description="Incoming HTTP Webhook received from external integration.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # WEB RSS
    # ============================================

    RSS_NEW_ENTRY = EventConfig(
        name="RSS_NEW_ENTRY",
        description="New entry in tracked RSS feed.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # Host Terminal
    # ============================================

    HOST_TERMINAL_MESSAGE = EventConfig(
        name="HOST_TERMINAL_MESSAGE",
        description="Incoming message from operator terminal.",
        level=EventLevel.CRITICAL,
        requires_attention=True,
    )

    HOST_TERMINAL_OPENED = EventConfig(
        name="HOST_TERMINAL_OPENED",
        description="Terminal UI window connected.",
        level=EventLevel.MEDIUM,
        requires_attention=False,
    )

    HOST_TERMINAL_CLOSED = EventConfig(
        name="HOST_TERMINAL_CLOSED",
        description="Terminal UI window disconnected.",
        level=EventLevel.LOW,
        requires_attention=False,
    )

    # ============================================
    # Email
    # ============================================

    EMAIL_INCOMING = EventConfig(
        name="EMAIL_INCOMING",
        description="Incoming email message.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # GITHUB
    # ============================================

    GITHUB_REPO_ACTIVITY = EventConfig(
        name="GITHUB_REPO_ACTIVITY",
        description="Activity event in tracked GitHub repository (push, issue, PR).",
        level=EventLevel.MEDIUM,
        requires_attention=True,
    )

    # ============================================
    # META
    # ============================================

    SYSTEM_DASHBOARD_UPDATE = EventConfig(
        name="SYSTEM_DASHBOARD_UPDATE",
        description="Passive custom dashboard block update from skills or sandbox.",
        level=EventLevel.INFO,
        requires_attention=False,
    )

    SYSTEM_CONFIG_UPDATED = EventConfig(
        name="SYSTEM_CONFIG_UPDATED",
        description="System configuration updated via Meta interface.",
        level=EventLevel.INFO,
        requires_attention=False,
    )

    # ============================================
    # CALENDAR
    # ============================================

    SYSTEM_CALENDAR_ALARM = EventConfig(
        name="SYSTEM_CALENDAR_ALARM",
        description="Calendar timer or scheduled alarm triggered.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # Swarm
    # ============================================

    SUBAGENT_TASK_COMPLETED = EventConfig(
        name="SUBAGENT_TASK_COMPLETED",
        description="Subagent finished execution and compiled a final report.",
        level=EventLevel.HIGH,
        requires_attention=True,
    )

    # ============================================
    # Subconscious
    # ============================================

    SUBCONSCIOUS_TRIGGERED = EventConfig(
        name="SUBCONSCIOUS_TRIGGERED",
        description="Subconscious cognitive process trigger.",
        level=EventLevel.BACKGROUND,
        requires_attention=False,
    )

    # ============================================
    # General System Events
    # ============================================

    SYSTEM_CORE_START = EventConfig(
        name="SYSTEM_CORE_START",
        description="System initialization completed.",
        level=EventLevel.CRITICAL,
        requires_attention=True,
    )

    SYSTEM_CORE_STOP = EventConfig(
        name="SYSTEM_CORE_STOP",
        description="System shutdown.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    SYSTEM_SHUTDOWN_REQUESTED = EventConfig(
        name="SYSTEM_SHUTDOWN_REQUESTED",
        description="Agent requested full system shutdown.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    SYSTEM_REBOOT_REQUESTED = EventConfig(
        name="SYSTEM_REBOOT_REQUESTED",
        description="Agent requested full system reboot.",
        level=EventLevel.CRITICAL,
        requires_attention=False,
    )

    SYSTEM_SLEEP_REQUESTED = EventConfig(
        name="SYSTEM_SLEEP_REQUESTED",
        description="Agent requested custom sleep duration and event sensitivity depth.",
        level=EventLevel.INFO,
        requires_attention=False,
    )

    REACT_TICK_SAVED = EventConfig(
        name="REACT_TICK_SAVED",
        description="Reasoning step successfully completed.",
        level=EventLevel.INFO,
        requires_attention=False,
    )

    @classmethod
    def all(cls) -> list[EventConfig]:
        events = []
        for attr_name, attr_value in vars(cls).items():
            if isinstance(attr_value, EventConfig):
                events.append(attr_value)
        return events


ALL_EVENTS = Events.all()
