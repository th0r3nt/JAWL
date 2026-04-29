import pytest
from src.l2_interfaces.telegram.aiogram.skills.chats import AiogramChats


@pytest.mark.asyncio
async def test_chats_get_chats(state, mock_client):
    """Тест: get_chats возвращает данные из кэша стейта."""
    skills = AiogramChats(mock_client, state)

    # Кэш пуст
    res_empty = await skills.get_chats()
    assert "Список чатов пуст" in res_empty.message

    # Имитируем заполненный кэш
    state._chats_cache[1] = "Chat 1"
    state._chats_cache[2] = "Chat 2"

    res = await skills.get_chats()
    assert res.is_success is True
    # Переворот списка должен вернуть Chat 2 первым
    assert "Chat 2\nChat 1" in res.message
