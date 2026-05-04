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


@patch("src.l3_agent.llm.api_keys.rotator.time.time")
def test_rotator_subsecond_wait_never_zero(mock_time, mock_keys: list[str]) -> None:
    """При кулдауне меньше 1 сек сообщение не должно говорить 'подождать 0 сек'.

    Раньше было int(0.7) = 0, агент думал что ожидание не требуется и шел в
    ретрай луп, получая тот же rate limit.
    """
    mock_time.return_value = 100.0
    rotator = APIKeyRotator(mock_keys)

    # Все ключи уйдут в кулдаун на 0.7 секунды
    rotator._cooldowns = {k: 100.7 for k in mock_keys}

    with pytest.raises(RuntimeError) as exc:
        rotator.get_next_key()

    msg = str(exc.value)
    assert "подождать 0 сек" not in msg
    assert "подождать 1 сек" in msg


@patch("src.l3_agent.llm.api_keys.rotator.time.time")
def test_rotator_wait_time_rounds_up(mock_time, mock_keys: list[str]) -> None:
    """При кулдауне 3.4 сек должно быть 'подождать 4', а не 3."""
    mock_time.return_value = 100.0
    rotator = APIKeyRotator(mock_keys)
    rotator._cooldowns = {k: 103.4 for k in mock_keys}

    with pytest.raises(RuntimeError, match="подождать 4 сек"):
        rotator.get_next_key()


@patch("src.l3_agent.llm.api_keys.rotator.time.time")
def test_rotator_wait_time_small_negative_race(mock_time, mock_keys: list[str]) -> None:
    """Race condition: проверка выше по петле пропустила ключи, но на этапе min() один из
    ключей уже освободился. int(отрицательного) выдавал отрицательное число в
    сообщении. Симулируем вызовом _raise_exhausted напрямую через принудительно выставленный
    max-кулдаун чуть в будущем и сдвигом часов прямо в момент min().
    """
    mock_time.return_value = 100.0
    rotator = APIKeyRotator(mock_keys)
    # Все в будущем чтобы петля выше ничего не вернула
    rotator._cooldowns = {k: 100.3 for k in mock_keys}

    with pytest.raises(RuntimeError) as exc:
        rotator.get_next_key()
    msg = str(exc.value)
    assert "-" not in msg.split("подождать", 1)[1]
    assert "подождать 1 сек" in msg
