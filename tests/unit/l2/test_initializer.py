import pytest
from unittest.mock import MagicMock, patch

from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.initializer import initialize_l2_interfaces
from src.utils.settings import InterfacesConfig


# Создаем фейковый плагин для тестов
class DummyPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "DUMMY PLUGIN"

    @property
    def description(self) -> str:
        return "Test description"

    def is_enabled(self, config) -> bool:
        return False

    def setup(self, container, env_vars):
        return ["dummy_worker"]


@pytest.mark.asyncio
async def test_base_interface_off_provider():
    """Тест: BaseInterface (родитель плагинов) корректно генерирует отключенные блоки контекста."""
    plugin = DummyPlugin()
    registry_mock = MagicMock()

    # Вызываем метод регистрации заглушки
    plugin.register_off_provider(registry_mock)

    # Проверяем, что провайдер зарегистрировался
    registry_mock.register_provider.assert_called_once()
    kwargs = registry_mock.register_provider.call_args[1]

    assert kwargs["name"] == "dummy_plugin"

    # Извлекаем саму асинхронную функцию-провайдер и вызываем её
    provider_func = kwargs["provider_func"]
    result = await provider_func(event_name="TEST", payload={})

    assert "### DUMMY PLUGIN [OFF]" in result
    assert "Test description" in result
    assert "disabled" in result


def test_initialize_l2_interfaces_all_off():
    """
    Тест: Инициализатор сканирует плагины. Если плагин выключен,
    он должен зарегистрировать OFF-заглушку в реестре контекста.
    """
    system_mock = MagicMock()

    # Создаем реальный конфиг и принудительно выключаем ВСЁ
    config = InterfacesConfig()
    config.host.os.enabled = False
    config.host.terminal.enabled = False
    config.telegram.telethon.enabled = False
    config.telegram.aiogram.enabled = False
    config.github.enabled = False
    config.email.enabled = False
    config.web.search.enabled = False
    config.web.http.enabled = False
    config.web.browser.enabled = False
    config.web.hooks.enabled = False
    config.web.rss.enabled = False
    config.meta.enabled = False
    config.multimodality.enabled = False
    config.calendar.enabled = False
    config.code_graph.enabled = False
    config.voice.stt.cloud.whisper.enabled = False
    config.voice.tts.cloud.edge.enabled = False
    config.voice.tts.cloud.elevenlabs.enabled = False

    system_mock.interfaces_config = config
    system_mock.context_registry = MagicMock()

    # Запускаем инициализатор (он просканирует реальную папку l2_interfaces)
    components = initialize_l2_interfaces(system_mock, env_vars={})

    # Так как всё выключено, активных воркеров/клиентов быть не должно
    assert len(components) == 0

    # Но для каждого выключенного плагина должна была вызваться регистрация заглушки
    assert system_mock.context_registry.register_provider.call_count >= 10


@patch("src.l2_interfaces.initializer.importlib.util.module_from_spec")
@patch("src.l2_interfaces.initializer.importlib.util.spec_from_file_location")
@patch("src.l2_interfaces.initializer.inspect.getmembers")
@patch("src.l2_interfaces.initializer.Path.rglob")
def test_initialize_l2_interfaces_discovery(
    mock_rglob, mock_getmembers, mock_spec_from_file, mock_module_from_spec
):
    """Тест: Инициализатор (Plugin Discovery) корректно находит плагин..."""
    from unittest.mock import MagicMock

    mock_plugin_path = MagicMock()
    mock_plugin_path.relative_to.return_value.with_suffix.return_value = "fake.plugin"
    mock_rglob.return_value = [mock_plugin_path]

    mock_getmembers.return_value = [("DummyPlugin", DummyPlugin)]

    # Мокаем importlib, чтобы он проemptyил фейковый путь
    mock_spec = MagicMock()
    mock_spec_from_file.return_value = mock_spec
    mock_module_from_spec.return_value = MagicMock()

    system_mock = MagicMock()

    # --- СЦЕНАРИЙ 1: Плагин ВЫКЛЮЧЕН ---
    DummyPlugin.is_enabled = lambda self, cfg: False

    components = initialize_l2_interfaces(system_mock, env_vars={})

    assert len(components) == 0
    system_mock.context_registry.register_provider.assert_called_once()

    # Сброс моков
    system_mock.context_registry.reset_mock()

    # --- СЦЕНАРИЙ 2: Плагин ВКЛЮЧЕН ---
    DummyPlugin.is_enabled = lambda self, cfg: True

    components = initialize_l2_interfaces(system_mock, env_vars={})

    assert len(components) == 1
    assert components[0] == "dummy_worker"  # Вернул то, что возвращает setup()
    system_mock.context_registry.register_provider.assert_not_called()
