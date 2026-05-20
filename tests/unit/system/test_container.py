import pytest
from src.system.container import SystemContainer
from src.utils.settings import SettingsConfig, InterfacesConfig
from src.utils.event.bus import EventBus


def test_system_container_no_magic_attributes():
    """
    Тест: SystemContainer больше не использует магический __getattr__.
    Обращение к несуществующим '..._state' атрибутам должно вызывать честную ошибку AttributeError,
    побуждая разработчиков использовать явный словарь l0_states.
    """
    container = SystemContainer(SettingsConfig(), InterfacesConfig(), EventBus())

    # Запихиваем фейковый стейт в словарь (как это делают плагины)
    container.l0_states["telethon"] = "Фейковый стейт"

    # Прямое обращение к словарю работает
    assert container.l0_states["telethon"] == "Фейковый стейт"

    # Обращение в стиле старой архитектуры должно жестко падать
    with pytest.raises(AttributeError, match="has no attribute 'telethon_state'"):
        _ = container.telethon_state

    with pytest.raises(AttributeError, match="has no attribute 'os_state'"):
        _ = container.os_state
