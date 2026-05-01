"""
Unit-тесты для ротатора API ключей (APIKeyRotator).

Используют mock времени (patch) для проверки корректности алгоритма
Round-Robin, временной блокировки ключей (Cooldown) и полного удаления (Ban).
"""

import pytest
from unittest.mock import patch

from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


@pytest.fixture
def mock_keys() -> list[str]:
    """Фикстура: базовый набор мок-ключей."""
    return ["key1", "key2", "key3"]


def test_rotator_init_empty_keys() -> None:
    """При пустом списке ключей ротатор должен падать при инициализации."""
    with pytest.raises(ValueError, match="LLM API keys not found"):
        APIKeyRotator([])


def test_rotator_round_robin(mock_keys: list[str]) -> None:
    """Ключи должны выдаваться по кругу (Round-Robin)."""
    rotator = APIKeyRotator(mock_keys)

    assert rotator.get_next_key() == "key1"
    assert rotator.get_next_key() == "key2"
    assert rotator.get_next_key() == "key3"
    assert rotator.get_next_key() == "key1"  # Круг замкнулся


@patch("src.l3_agent.llm.api_keys.rotator.time.time")
def test_rotator_cooldown(mock_time, mock_keys: list[str]) -> None:
    """
    Если ключ ушел в кулдаун, ротатор должен переключиться на следующий
    и вернуть заблокированный только по истечении времени.
    """
    mock_time.return_value = 100.0  # Устанавливаем фиктивное время: 100 секунд

    rotator = APIKeyRotator(mock_keys)

    # Берем первый ключ и отправляем его в бан на 60 сек
    assert rotator.get_next_key() == "key1"
    rotator.cooldown_key("key1", seconds=60)

    # key1 теперь заблокирован до time=160.0. Следующий должен быть key2
    assert rotator.get_next_key() == "key2"
    assert rotator.get_next_key() == "key3"

    # Круг замкнулся. key1 все еще в бане, поэтому ротатор должен пропустить его и выдать key2
    assert rotator.get_next_key() == "key2"

    # Эмулируем прошествие времени: теперь time=161.0 (кулдаун key1 прошел)
    mock_time.return_value = 161.0

    # После key2 идет key3, а затем key1 должен снова стать доступен
    assert rotator.get_next_key() == "key3"
    assert rotator.get_next_key() == "key1"


def test_rotator_ban_key(mock_keys: list[str]) -> None:
    """Забаненный ключ (например при HTTP 401) должен навсегда удаляться из пула."""
    rotator = APIKeyRotator(mock_keys)

    rotator.ban_key("key2")

    assert rotator.total_keys() == 2
    assert rotator.get_next_key() == "key1"
    assert rotator.get_next_key() == "key3"
    assert rotator.get_next_key() == "key1"


@patch("src.l3_agent.llm.api_keys.rotator.time.time")
def test_rotator_all_keys_exhausted(mock_time, mock_keys: list[str]) -> None:
    """Если все ключи ушли в кулдаун, ротатор должен выкинуть RuntimeError."""
    mock_time.return_value = 100.0

    rotator = APIKeyRotator(mock_keys)

    rotator.cooldown_key("key1", 60)
    rotator.cooldown_key("key2", 60)
    rotator.cooldown_key("key3", 60)

    with pytest.raises(RuntimeError, match="Все API ключи исчерпали лимиты"):
        rotator.get_next_key()
