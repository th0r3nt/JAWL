import pytest
from unittest.mock import AsyncMock

from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages


@pytest.mark.asyncio
async def test_send_message_to_terminal_skill(terminal_client):
    """Тест: Навык агента успешно делегирует отправку клиенту."""

    skill = HostTerminalMessages(terminal_client)
    terminal_client.broadcast_message = AsyncMock()

    res = await skill.send_message_to_terminal("Команда выполнена")

    assert res.is_success is True
    terminal_client.broadcast_message.assert_called_once_with("Команда выполнена")


@pytest.mark.asyncio
async def test_send_message_to_terminal_skill_error(terminal_client):
    """Тест: Обработка внутренней ошибки при броадкасте."""

    skill = HostTerminalMessages(terminal_client)
    terminal_client.broadcast_message = AsyncMock(side_effect=Exception("Socket Error"))

    res = await skill.send_message_to_terminal("Команда выполнена")

    assert res.is_success is False
    assert "Socket Error" in res.message
