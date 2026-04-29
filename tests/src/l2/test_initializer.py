import pytest
from unittest.mock import MagicMock, patch

from src.l2_interfaces.initializer import make_off_provider, initialize_l2_interfaces


@pytest.mark.asyncio
async def test_make_off_provider():
    """Тест: Фабрика заглушек корректно генерирует отключенные блоки контекста."""
    provider = make_off_provider("TEST_MODULE")

    # Провайдер должен принимать любые kwargs и возвращать строку
    result = await provider(event_name="TEST", payload={})

    assert "### TEST_MODULE [OFF]" in result
    assert "отключен" in result


def test_initialize_l2_interfaces_all_off():
    """Тест: Если все интерфейсы выключены, инициализатор должен зарегистрировать OFF-заглушки для всех."""
    system_mock = MagicMock()

    # Настраиваем конфиг так, чтобы ВСЁ было выключено
    config_mock = MagicMock()
    config_mock.host.os.enabled = False
    config_mock.host.terminal.enabled = False
    config_mock.telegram.telethon.enabled = False
    config_mock.telegram.aiogram.enabled = False
    config_mock.github.enabled = False
    config_mock.email.enabled = False
    config_mock.web.search.enabled = False
    config_mock.web.http.enabled = False
    config_mock.web.browser.enabled = False
    config_mock.web.hooks.enabled = False
    config_mock.web.rss.enabled = False
    config_mock.meta.enabled = False
    config_mock.multimodality.enabled = False
    config_mock.calendar.enabled = False

    system_mock.interfaces_config = config_mock

    components = initialize_l2_interfaces(system_mock, env_vars={})

    # Ни один активный компонент не должен быть возвращен
    assert len(components) == 0

    # Проверяем, что в реестр контекста улетели заглушки
    registry_mock = system_mock.context_registry

    # Вызовов должно быть много (по одному на каждый отключенный интерфейс)
    assert registry_mock.register_provider.call_count >= 10

    # Убеждаемся, что среди вызовов был host os
    calls = registry_mock.register_provider.call_args_list
    host_os_called = any(call[0][0] == "host os" for call in calls)
    assert host_os_called is True


@patch("src.l2_interfaces.initializer.setup_host_terminal")
@patch("src.l2_interfaces.initializer.setup_host_os")
def test_initialize_l2_interfaces_some_on(mock_setup_os, mock_setup_terminal):
    """Тест: Инициализатор корректно дергает setup_* функции включенных модулей."""
    system_mock = MagicMock()

    config_mock = MagicMock()
    # Включаем только OS и Terminal
    config_mock.host.os.enabled = True
    config_mock.host.terminal.enabled = True
    # Все остальное выключено
    config_mock.telegram.telethon.enabled = False
    config_mock.telegram.aiogram.enabled = False
    config_mock.github.enabled = False
    config_mock.email.enabled = False
    config_mock.web.search.enabled = False
    config_mock.web.http.enabled = False
    config_mock.web.browser.enabled = False
    config_mock.web.hooks.enabled = False
    config_mock.web.rss.enabled = False
    config_mock.meta.enabled = False
    config_mock.multimodality.enabled = False
    config_mock.calendar.enabled = False

    system_mock.interfaces_config = config_mock

    # Моки возвращают фиктивные компоненты
    mock_setup_os.return_value = ["os_event_worker"]
    mock_setup_terminal.return_value = ["term_client", "term_worker"]

    components = initialize_l2_interfaces(system_mock, env_vars={})

    # Должен собрать компоненты из всех setup_ функций
    assert len(components) == 3
    assert "os_event_worker" in components
    assert "term_client" in components

    mock_setup_os.assert_called_once_with(system_mock)
    mock_setup_terminal.assert_called_once_with(system_mock)
