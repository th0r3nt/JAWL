import pytest
import asyncio
import aiohttp
from unittest.mock import MagicMock

from src.utils.settings import WebHooksConfig

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l2_interfaces.web.hooks.state import WebHooksState
from src.l2_interfaces.web.hooks.client import WebHooksClient
from src.l2_interfaces.web.hooks.events import WebHooksEvents


@pytest.mark.asyncio
async def test_integration_real_http_webhook_to_eventbus():
    """
    Хардкорный E2E тест: "Внешний мир -> HTTP Сеть -> Aiohttp Сервер -> EventBus -> L0 State".
    Поднимает реальный сервер на случайном порту, отправляет реальный HTTP POST запрос
    с токеном и проверяет, что архитектура пропускает данные по всем слоям до кэша агента.
    """

    # 1. Поднимаем реальную шину событий
    bus = EventBus()
    event_receiver = MagicMock()
    event_receiver.__name__ = "mock_webhook_receiver"
    bus.subscribe(Events.WEBHOOK_MESSAGE_INCOMING, event_receiver)

    # 2. Настраиваем WebHooks (порт 0 означает, что ОС сама выдаст любой свободный порт)
    config = WebHooksConfig(enabled=True, host="127.0.0.1", port=0, history_limit=5)
    state = WebHooksState()
    client = WebHooksClient(state=state, config=config, secret_token="my_super_secret")

    events_worker = WebHooksEvents(client=client, state=state, event_bus=bus, timezone=3)

    # 3. Запускаем сервер
    await events_worker.start()

    # Достаем реальный выданный порт
    actual_port = events_worker.runner.addresses[0][1]

    try:
        # 4. Выступаем в роли стороннего сервиса (например, GitHub Actions)
        # Отправляем реальный HTTP запрос через сеть
        async with aiohttp.ClientSession() as session:
            url = f"http://127.0.0.1:{actual_port}/webhook/github_ci?token=my_super_secret"
            payload = {"build": "failed", "commit": "1a2b3c"}

            async with session.post(url, json=payload) as response:
                assert response.status == 200
                resp_json = await response.json()
                assert resp_json["status"] == "ok"
                hook_id = resp_json["id"]

        # Даем EventBus время на обработку фоновых задач
        if bus.background_tasks:
            await asyncio.gather(*bus.background_tasks)

        # 5. ПРОВЕРКИ
        # А) Проверяем L0 State (Агент должен увидеть это на приборной панели)
        assert len(state.recent_hooks) == 1
        assert state.recent_hooks[0]["id"] == hook_id
        assert state.recent_hooks[0]["source"] == "github_ci"
        assert state.recent_hooks[0]["payload"]["build"] == "failed"

        # Б) Проверяем, что шина проснулась (Heartbeat получит сигнал)
        event_receiver.assert_called_once()
        kwargs = event_receiver.call_args[1]
        assert kwargs["source"] == "github_ci"
        assert "build" in kwargs["preview"]
        assert "failed" in kwargs["preview"]

    finally:
        # 6. Обязательно глушим сервер, чтобы не оставить висящих сокетов
        await events_worker.stop()
