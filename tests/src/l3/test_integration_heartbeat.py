import pytest
import asyncio
from unittest.mock import AsyncMock

from src.main import System
from src.utils.event.bus import EventBus
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events
from src.utils.settings import SettingsConfig, InterfacesConfig
from src.l3_agent.heartbeat import Heartbeat


@pytest.mark.asyncio
async def test_integration_eventbus_wakes_heartbeat():
    """
    Интеграционный тест: "Уши -> Мозг".
    Проверяет, что публикация CRITICAL события в шину прерывает долгий сон Heartbeat
    и экстренно запускает ReAct цикл с правильной причиной.
    """

    # 1. Поднимаем реальную шину и мост
    bus = EventBus()
    system = System(bus, SettingsConfig(), InterfacesConfig())

    bridge = EventBridge(system)
    bridge.setup_routing()  # Подписываем Heartbeat на события

    # 2. Поднимаем реальный Heartbeat (с фейковым ReactLoop, чтобы не дергать LLM)
    mock_react_loop = AsyncMock()

    # Ставим сон на 1 час (3600 сек)
    hb = Heartbeat(
        react_loop=mock_react_loop,
        heartbeat_interval=3600,
        continuous_cycle=False,
        accel_config=system.settings.system.event_acceleration,
        timezone=3,
    )
    system.heartbeat = hb

    # 3. Запускаем Heartbeat в фоне
    hb_task = asyncio.create_task(hb.start())

    # Даем Event Loop'у миллисекунду, чтобы Heartbeat успел уснуть
    await asyncio.sleep(0.01)

    # Публикуем реальное событие
    await bus.publish(Events.HOST_TERMINAL_MESSAGE, message="Проснись, самурай")

    # Ждем, пока шина отработает все подписки
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # Даем Heartbeat миллисекунду на реакцию
    await asyncio.sleep(0.01)

    # 5. Проверяем результаты
    # ReAct цикл должен был запуститься несмотря на то, что час еще не прошел
    mock_react_loop.run.assert_awaited_once()

    call_kwargs = mock_react_loop.run.call_args[1]
    assert call_kwargs["event_name"] == Events.HOST_TERMINAL_MESSAGE.name
    assert call_kwargs["payload"]["message"] == "Проснись, самурай"

    # Гасим фоновую задачу
    hb.stop()
    await hb_task
