import pytest
import json
import socket
from unittest.mock import MagicMock, AsyncMock
from aiohttp import web
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_webhook_auth_failure(hooks_events):
    """Тест: Отклонение вебхука при неверном токене (401)."""
    req = MagicMock(spec=web.Request)
    req.query = {"token": "wrong_token"}
    req.headers = {}
    req.remote = "127.0.0.1"

    resp = await hooks_events.handle_webhook(req)
    assert resp.status == 401

    # Проверяем, что в стейт ничего не попало
    assert len(hooks_events.state.recent_hooks) == 0


@pytest.mark.asyncio
async def test_webhook_auth_uses_constant_time_compare(hooks_events, monkeypatch):
    """Тест: сравнение токена должно идти через hmac.compare_digest (защита от timing attack)."""
    import src.l2_interfaces.web.hooks.events as events_module

    original_compare = events_module.hmac.compare_digest
    calls = {"count": 0}

    def spy_compare(a, b):
        calls["count"] += 1
        return original_compare(a, b)

    monkeypatch.setattr(events_module.hmac, "compare_digest", spy_compare)

    req = MagicMock(spec=web.Request)
    req.query = {"token": "wrong_token"}
    req.headers = {}
    req.remote = "127.0.0.1"

    resp = await hooks_events.handle_webhook(req)
    assert resp.status == 401
    # Именно compare_digest должен был вызваться (а не !=).
    assert calls["count"] >= 1


@pytest.mark.asyncio
async def test_webhook_auth_missing_token_rejected(hooks_events):
    """Тест: запрос без токена должен отклоняться (раньше None != secret тоже отклонял,
    но теперь compare_digest(None, ...) кинул бы TypeError — страхуемся от регрессии)."""
    req = MagicMock(spec=web.Request)
    req.query = {}
    req.headers = {}
    req.remote = "127.0.0.1"

    resp = await hooks_events.handle_webhook(req)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_webhook_json_success(hooks_events, mock_bus):
    """Тест: Успешная обработка JSON вебхука и публикация в шину."""
    req = MagicMock(spec=web.Request)
    req.query = {"token": "secret123"}  # Авторизация по query
    req.headers = {}
    req.match_info = {"source": "github_action"}
    req.json = AsyncMock(return_value={"status": "success"})

    resp = await hooks_events.handle_webhook(req)
    assert resp.status == 200

    # Проверка L0 State
    assert len(hooks_events.state.recent_hooks) == 1
    assert hooks_events.state.recent_hooks[0]["source"] == "github_action"
    assert hooks_events.state.recent_hooks[0]["payload"]["status"] == "success"

    # Проверка публикации в EventBus
    mock_bus.publish.assert_called_once()
    args = mock_bus.publish.call_args
    assert args[0][0] == Events.WEBHOOK_MESSAGE_INCOMING
    assert args[1]["source"] == "github_action"


@pytest.mark.asyncio
async def test_webhook_text_success(hooks_events, mock_bus):
    """Тест: Обработка сырого текста (Fallback если не JSON) и авторизация по Header."""
    req = MagicMock(spec=web.Request)
    req.query = {}
    req.headers = {"Authorization": "Bearer secret123"}  # Авторизация по хедеру
    req.match_info = {"source": "plain_service"}

    # Имитируем падение json() для перехода в блок text()
    req.json = AsyncMock(side_effect=json.JSONDecodeError("Expect value", "doc", 0))
    req.text = AsyncMock(return_value="Some raw text payload")

    resp = await hooks_events.handle_webhook(req)

    assert resp.status == 200
    assert hooks_events.state.recent_hooks[0]["payload"] == "Some raw text payload"


@pytest.mark.asyncio
async def test_webhook_port_collision_graceful_degradation(hooks_events):
    """
    Тест: Изящная деградация (Graceful Degradation).
    Если порт уже занят другим приложением ОС, сервер не должен крашить агента.
    Он должен просто залогировать ошибку и оставить is_online = False.
    """
    host = hooks_events.client.config.host
    port = hooks_events.client.config.port

    # Искусственно занимаем порт на уровне операционной системы
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.listen(1)

        # Пытаемся запустить сервер вебхуков
        await hooks_events.start()

        # Сервер не должен был запуститься
        assert hooks_events.state.is_online is False
        assert hooks_events.runner is None

    finally:
        # Обязательно освобождаем порт после теста
        sock.close()
