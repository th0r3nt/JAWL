import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from src.utils.event.registry import Events
from src.l2_interfaces.host.os.polls.daemons import DaemonsPoller


@pytest.mark.asyncio
async def test_daemons_sandbox_webhook(os_client):
    """Тест: сбор вебхуков из песочницы (jawl_api)."""
    bus_mock = MagicMock()
    bus_mock.publish = AsyncMock()
    
    poller = DaemonsPoller(os_client, os_client.state, bus_mock)
    
    # Создаем фейковый вебхук
    events_dir = os_client.events_dir
    webhook_file = events_dir / "12345_abc.json"
    
    webhook_data = {"message": "Скрипт завершен", "payload": {"count": 10}}
    webhook_file.write_text(json.dumps(webhook_data), encoding="utf-8")
    
    await poller._poll_sandbox_events()
    
    # Проверяем, что ивент улетел в шину
    bus_mock.publish.assert_called_once_with(
        Events.HOST_OS_SANDBOX_EVENT, 
        message="Скрипт завершен", 
        count=10
    )
    
    # Файл должен быть удален
    assert not webhook_file.exists()