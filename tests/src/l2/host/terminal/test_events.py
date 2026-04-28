import pytest
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_terminal_events_loop(terminal_client, mock_bus):
    """Тест: Фоновый воркер читает очередь и отправляет события в EventBus."""
    events = HostTerminalEvents(terminal_client, mock_bus)
    events._is_running = True

    # Кладем сырое сообщение в асинхронную очередь клиента (как это делает TCP-сервер)
    await terminal_client.incoming_queue.put("Выполни скрипт")

    # Перехватываем вызов publish, чтобы остановить бесконечный цикл после 1 итерации
    async def fake_publish(*args, **kwargs):
        events._is_running = False

    mock_bus.publish.side_effect = fake_publish

    # Запускаем цикл
    await events._loop()

    # Проверяем, что событие нужного типа улетело в шину
    mock_bus.publish.assert_called_once_with(
        Events.HOST_TERMINAL_MESSAGE, sender_name="User", message="Выполни скрипт"
    )
