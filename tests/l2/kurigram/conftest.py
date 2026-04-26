import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.event.bus import EventBus
from src.l0_state.interfaces.state import KurigramState
from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l2_interfaces.telegram.kurigram.events import KurigramEvents


async def async_generator(items):
    """Хелпер для имитации асинхронных генераторов клиента."""
    for item in items:
        yield item


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.anyio)


@pytest.fixture
def mock_kurigram_client():
    """Создает мок клиента Telegram с нейтральным API."""
    wrapper = MagicMock(spec=KurigramClient)
    inner_client = MagicMock()

    for method in (
        "add_contact",
        "ban_chat_member",
        "block_user",
        "create_channel",
        "create_forum_topic",
        "create_supergroup",
        "delete_messages",
        "edit_message_text",
        "export_chat_invite_link",
        "get_chat",
        "get_me",
        "get_messages",
        "invoke",
        "join_chat",
        "leave_chat",
        "pin_chat_message",
        "promote_chat_member",
        "read_chat_history",
        "resolve_peer",
        "restrict_chat_member",
        "send_message",
        "send_poll",
        "send_reaction",
        "set_chat_description",
        "set_chat_photo",
        "set_chat_title",
        "set_chat_username",
        "set_profile_photo",
        "unban_chat_member",
        "unblock_user",
        "unpin_chat_message",
        "update_profile",
        "vote_poll",
    ):
        setattr(inner_client, method, AsyncMock())

    inner_client.get_chat_history = MagicMock(return_value=async_generator([]))
    inner_client.get_dialogs = MagicMock(return_value=async_generator([]))
    inner_client.get_discussion_replies = MagicMock(return_value=async_generator([]))
    inner_client.search_messages = MagicMock(return_value=async_generator([]))
    inner_client.invoke.return_value = None

    wrapper.client.return_value = inner_client
    wrapper.timezone = 3
    return wrapper


@pytest.fixture
def mock_bus():
    """Создает мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def state():
    return KurigramState(number_of_last_chats=2)


@pytest.fixture
def kurigram_events(mock_kurigram_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return KurigramEvents(mock_kurigram_client, state, mock_bus)
