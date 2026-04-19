import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon.tl.types import UpdateMessageReactions

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.l0_state.interfaces.state import TelethonState

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages
from src.l2_interfaces.telegram.telethon.skills.account import TelethonAccount
from src.l2_interfaces.telegram.telethon.skills.chats import TelethonChats
from src.l2_interfaces.telegram.telethon.skills.moderation import TelethonModeration
from src.l2_interfaces.telegram.telethon.skills.polls import TelethonPolls
from src.l2_interfaces.telegram.telethon.skills.reactions import TelethonReactions


# ===================================================================
# HELPERS & MOCKS
# ===================================================================


async def async_generator(items):
    """Хелпер для создания асинхронных генераторов (имитация iter_dialogs)."""
    for item in items:
        yield item


@pytest.fixture
def mock_tg_client():
    """Создает мок клиента Telethon."""
    wrapper = MagicMock(spec=TelethonClient)
    inner_client = AsyncMock()

    # iter_dialogs в Telethon возвращает асинхронный генератор мгновенно (без await)
    # Поэтому мы переопределяем этот метод обычным MagicMock, чтобы он не создавал корутину
    inner_client.iter_dialogs = MagicMock()

    wrapper.client.return_value = inner_client
    return wrapper


@pytest.fixture
def mock_bus():
    """Создает мок шины событий."""
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def state():
    """Стейт на 2 чата."""
    return TelethonState(number_of_last_chats=2)


@pytest.fixture
def telethon_events(mock_tg_client, state, mock_bus):
    """Инициализированный обработчик событий."""
    return TelethonEvents(mock_tg_client, state, mock_bus)


# ===================================================================
# TESTS: EVENTS & STATE
# ===================================================================


@pytest.mark.asyncio
async def test_update_state(telethon_events, mock_tg_client, state):
    """Тест: парсинг диалогов и правильное форматирование в TelethonState."""

    # Имитируем два диалога
    dlg1 = MagicMock()
    dlg1.is_user = True
    dlg1.is_group = False
    dlg1.id = 111
    dlg1.name = "Иван"
    dlg1.unread_count = 1

    dlg2 = MagicMock()
    dlg2.is_user = False
    dlg2.is_group = True
    dlg2.id = 222
    dlg2.name = "Dev Chat"
    dlg2.unread_count = 0

    mock_tg_client.client().iter_dialogs.return_value = async_generator([dlg1, dlg2])

    await telethon_events._update_state()

    # Проверяем, что стейт правильно отформатирован
    assert "User | ID: 111 | Название: Иван [Непрочитанных: 1]" in state.last_chats
    assert "Group | ID: 222 | Название: Dev Chat" in state.last_chats


@pytest.mark.asyncio
@patch("src.l2_interfaces.telegram.telethon.events.utils.get_display_name")
async def test_on_private_message(mock_get_display_name, telethon_events, mock_bus):
    """Тест: личное сообщение публикует правильный ивент."""

    # Заставляем утилиту Telethon всегда возвращать "Alex" в рамках этого теста
    mock_get_display_name.return_value = "Alex"

    # Имитируем входящий ивент (сообщение)
    event = MagicMock()
    event.text = "Привет, агент!"
    event.chat_id = 12345

    sender = MagicMock()
    event.get_sender = AsyncMock(return_value=sender)

    # Пустая история диалогов, чтобы _update_state не упал
    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_private_message(event)

    # Проверяем публикацию в шину
    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_INCOMING,
        message="Привет, агент!",
        sender_name="Alex",
        chat_id=12345,
    )


@pytest.mark.asyncio
async def test_on_group_message_mentioned(telethon_events, mock_bus):
    """Тест: сообщение в группе с упоминанием публикует MENTION ивент."""
    event = MagicMock()
    event.text = "@agent, как дела?"
    event.chat_id = -100999
    event.mentioned = True  # НАС ТЕГНУЛИ
    event.get_sender = AsyncMock(return_value=None)  # Без имени

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_GROUP_MENTION,
        message="@agent, как дела?",
        sender_name="Unknown",
        chat_id=-100999,
    )


@pytest.mark.asyncio
async def test_on_group_message_ignored(telethon_events, mock_bus):
    """Тест: обычное сообщение в группе публикует фоновый ивент (шум)."""
    event = MagicMock()
    event.text = "Просто текст"
    event.chat_id = -100999
    event.mentioned = False  # НАС НЕ ТЕГАЛИ
    event.get_sender = AsyncMock(return_value=None)

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_group_message(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_GROUP_MESSAGE,
        message="Просто текст",
        sender_name="Unknown",
        chat_id=-100999,
    )


@pytest.mark.asyncio
async def test_on_reaction(telethon_events, mock_bus):
    """Тест: реакции обрабатываются корректно."""
    # Имитируем сырой объект реакции
    event = UpdateMessageReactions(peer=MagicMock(), msg_id=42, reactions=MagicMock())

    telethon_events.tg_client.client().iter_dialogs.return_value = async_generator([])

    await telethon_events._on_reaction(event)

    mock_bus.publish.assert_called_once_with(
        Events.TELETHON_MESSAGE_REACTION,
        chat_id="Unknown",
        message_id=42,
        reactions="Реакции удалены",
    )


# ===================================================================
# TESTS: SKILLS
# ===================================================================


@pytest.mark.asyncio
async def test_send_message_skill(mock_tg_client):
    """Тест навыка агента: отправка сообщения."""
    skills = TelethonMessages(mock_tg_client)

    # Имитируем возвращаемый объект отправленного сообщения
    sent_msg = MagicMock()
    sent_msg.id = 999
    mock_tg_client.client().send_message = AsyncMock(return_value=sent_msg)

    res = await skills.send_message(to_id=123, text="Test")

    assert res.is_success is True
    assert "999" in res.message

    mock_tg_client.client().send_message.assert_called_once_with(
        entity=123, message="Test", silent=False
    )


@pytest.mark.asyncio
async def test_send_message_with_topic_skill(mock_tg_client):
    """Тест навыка агента: отправка сообщения в конкретный топик форума."""
    skills = TelethonMessages(mock_tg_client)

    sent_msg = MagicMock()
    sent_msg.id = 777
    mock_tg_client.client().send_message = AsyncMock(return_value=sent_msg)

    # Передаем topic_id = 5238
    res = await skills.send_message(to_id=-100123, text="Test Topic", topic_id=5238)

    assert res.is_success is True
    assert "777" in res.message

    # Telethon под капотом использует reply_to для отправки в топики
    mock_tg_client.client().send_message.assert_called_once_with(
        entity=-100123, message="Test Topic", silent=False, reply_to=5238
    )


# ===================================================================
# TESTS: TELETHON ACCOUNT
# ===================================================================


@pytest.mark.asyncio
async def test_account_change_username(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.update_profile_state = AsyncMock()

    res = await skills.change_username(name="Neo", surname="Anderson")
    assert res.is_success is True
    assert "Neo Anderson" in res.message
    mock_tg_client.update_profile_state.assert_called_once()


@pytest.mark.asyncio
async def test_account_change_bio(mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.update_profile_state = AsyncMock()

    res = await skills.change_bio(text="Wake up, Neo")
    assert res.is_success is True
    mock_tg_client.update_profile_state.assert_called_once()


@pytest.mark.asyncio
@patch("os.path.exists", return_value=True)
async def test_account_change_avatar(mock_exists, mock_tg_client):
    skills = TelethonAccount(mock_tg_client)
    mock_tg_client.client().upload_file = AsyncMock(return_value="mocked_file")

    res = await skills.change_avatar(filepath="/fake/path/avatar.jpg")
    assert res.is_success is True
    mock_tg_client.client().upload_file.assert_called_once_with("/fake/path/avatar.jpg")


# ===================================================================
# TESTS: TELETHON CHATS
# ===================================================================


@pytest.mark.asyncio
async def test_chats_mark_as_read(mock_tg_client):
    skills = TelethonChats(mock_tg_client)
    mock_tg_client.client().get_entity = AsyncMock(return_value="mock_entity")

    res = await skills.mark_as_read(chat_id=123)
    assert res.is_success is True
    mock_tg_client.client().send_read_acknowledge.assert_called_once_with("mock_entity")


@pytest.mark.asyncio
async def test_chats_join_chat(mock_tg_client):
    skills = TelethonChats(mock_tg_client)

    # 1. По юзернейму
    res_username = await skills.join_chat("durov")
    assert res_username.is_success is True

    # 2. По приватной ссылке
    res_link = await skills.join_chat("https://t.me/joinchat/AAAAAE")
    assert res_link.is_success is True


# ===================================================================
# TESTS: TELETHON MESSAGES (Extra)
# ===================================================================


@pytest.mark.asyncio
async def test_messages_delete_message(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    res = await skills.delete_message(msg_id=42, chat_id=123)

    assert res.is_success is True
    mock_tg_client.client().delete_messages.assert_called_once_with(
        entity=123, message_ids=[42]
    )


@pytest.mark.asyncio
async def test_messages_edit_message(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)
    res = await skills.edit_message(msg_id=42, new_text="Fixed", chat_id=123)

    assert res.is_success is True
    mock_tg_client.client().edit_message.assert_called_once_with(
        entity=123, message=42, text="Fixed"
    )


@pytest.mark.asyncio
async def test_messages_click_inline_button(mock_tg_client):
    skills = TelethonMessages(mock_tg_client)

    # Имитируем сообщение с кнопкой
    mock_msg = MagicMock()
    mock_btn = MagicMock()
    mock_btn.text = "Accept"
    mock_msg.buttons = [[mock_btn]]
    mock_msg.click = AsyncMock(return_value=MagicMock(message="Success callback"))

    mock_tg_client.client().get_messages = AsyncMock(return_value=mock_msg)

    res = await skills.click_inline_button(chat_id=123, message_id=42, button_text="acc")

    assert res.is_success is True
    assert "Success callback" in res.message
    mock_msg.click.assert_called_once_with(0, 0)  # Координаты кнопки i, j


# ===================================================================
# TESTS: TELETHON MODERATION
# ===================================================================


@pytest.mark.asyncio
async def test_moderation_ban_global(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    res = await skills.ban_user(user_id=123)

    assert res.is_success is True
    assert "глобальный ЧС" in res.message


@pytest.mark.asyncio
async def test_moderation_ban_in_chat(mock_tg_client):
    skills = TelethonModeration(mock_tg_client)
    mock_tg_client.client().edit_permissions = AsyncMock()

    res = await skills.ban_user(user_id=123, chat_id=-100500)

    assert res.is_success is True
    assert "забанен в чате" in res.message
    mock_tg_client.client().edit_permissions.assert_called_once_with(
        -100500, 123, view_messages=False
    )


# ===================================================================
# TESTS: TELETHON POLLS
# ===================================================================


@pytest.mark.asyncio
async def test_polls_create_poll(mock_tg_client):
    skills = TelethonPolls(mock_tg_client)
    mock_sent_msg = MagicMock(id=888)
    mock_tg_client.client().send_message = AsyncMock(return_value=mock_sent_msg)

    res = await skills.create_poll(
        chat_id=123, question="Tea or Coffee?", options=["Tea", "Coffee"]
    )

    assert res.is_success is True
    assert "888" in res.message
    mock_tg_client.client().send_message.assert_called_once()


@pytest.mark.asyncio
async def test_polls_vote_in_poll(mock_tg_client):
    skills = TelethonPolls(mock_tg_client)

    # Собираем фейковый опрос
    mock_msg = MagicMock()
    mock_msg.poll.poll.closed = False
    mock_ans = MagicMock()
    mock_ans.option = b"1"
    mock_msg.poll.poll.answers = [mock_ans]

    mock_tg_client.client().get_messages = AsyncMock(return_value=mock_msg)
    mock_tg_client.client().get_input_entity = AsyncMock(return_value="entity")

    res = await skills.vote_in_poll(chat_id=123, message_id=42, option_indices=[0])

    assert res.is_success is True
    # Вызов client() с SendVoteRequest
    assert mock_tg_client.client().call_count >= 1


# ===================================================================
# TESTS: TELETHON REACTIONS
# ===================================================================


@pytest.mark.asyncio
async def test_reactions_set_reaction(mock_tg_client):
    skills = TelethonReactions(mock_tg_client)
    res = await skills.set_reaction(chat_id=123, message_id=42, reaction="👍")

    assert res.is_success is True
    # Проверка, что сырой вызов API был осуществлен
    assert mock_tg_client.client().call_count >= 1


@pytest.mark.asyncio
async def test_reactions_remove_reaction(mock_tg_client):
    skills = TelethonReactions(mock_tg_client)
    res = await skills.remove_reaction(chat_id=123, message_id=42)

    assert res.is_success is True


# ===================================================================
# TESTS: COMPLEX CHAT PARSING (read_chat)
# ===================================================================


@pytest.mark.asyncio
async def test_chats_read_chat_complex_parsing(mock_tg_client):
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    skills = TelethonChats(mock_tg_client)

    mock_tg_client.timezone = 3

    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.date = datetime(2023, 10, 10, 15, 0, tzinfo=timezone.utc)
    mock_msg.action = None

    mock_sender = MagicMock()
    mock_sender.first_name = "Th0r3nt"
    mock_msg.sender = mock_sender
    mock_msg.sender_id = 999

    mock_msg.text = "Смотри мем"
    mock_msg.photo = True

    mock_fwd = MagicMock()
    mock_fwd.from_name = "Meme Channel"
    mock_msg.fwd_from = mock_fwd
    mock_msg.get_forward_sender = AsyncMock(return_value=None)

    mock_reply = MagicMock()
    mock_reply.reply_to_msg_id = 42
    mock_reply.forum_topic = False
    mock_msg.reply_to = mock_reply

    mock_reaction = MagicMock()
    mock_reaction.reaction.emoticon = "🔥"
    mock_reaction.count = 5
    mock_msg.reactions.results = [mock_reaction]

    mock_btn = MagicMock()
    mock_btn.text = "Лайк"
    mock_msg.buttons = [[mock_btn]]

    async def async_generator(items):
        for item in items:
            yield item

    mock_tg_client.client().iter_messages = MagicMock(return_value=async_generator([mock_msg]))
    mock_tg_client.client().get_entity = AsyncMock(return_value="mock_entity")
    mock_tg_client.client().get_messages = AsyncMock(return_value=None)

    res = await skills.read_chat(chat_id=123, limit=1)

    assert res.is_success is True, res.message
    assert "[Фотография] Смотри мем" in res.message
    assert "[Переслано от: Meme Channel]" in res.message
    assert "(В ответ на сообщение ID 42 от Unknown)" in res.message
    assert "[Реакции: 🔥 5]" in res.message
    assert "[Кнопки: [Лайк]]" in res.message


@pytest.mark.asyncio
async def test_chats_add_contact(mock_tg_client):
    skills = TelethonChats(mock_tg_client)

    # Мокаем получение entity пользователя
    mock_tg_client.client().get_input_entity = AsyncMock(return_value="mock_user")

    res = await skills.add_contact(user_id="durov", first_name="Pavel", last_name="Durov")

    assert res.is_success is True
    assert "добавлен в контакты" in res.message

    # Проверяем, что был сырой вызов API к Telegram
    assert mock_tg_client.client().call_count >= 1
