import pytest
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator

# ===================================================================
# TESTS
# ===================================================================


def test_rotator_initialization():
    """Тест: ключи успешно загружаются в ротатор."""
    keys = ["key_1", "key_2", "key_3"]
    rotator = APIKeyRotator(keys=keys)

    assert rotator.total_keys() == 3
    assert rotator.keys[0] == "key_1"
    assert rotator.keys[2] == "key_3"


def test_rotator_round_robin():
    """Тест: ключи выдаются по кругу."""
    rotator = APIKeyRotator(keys=["key_1", "key_2"])

    # Первый круг
    assert rotator.get_next_key() == "key_1"
    assert rotator.get_next_key() == "key_2"

    # Второй круг (вернулись к началу)
    assert rotator.get_next_key() == "key_1"
    assert rotator.get_next_key() == "key_2"


def test_rotator_empty_keys_raises_error():
    """Тест: если список ключей пуст, система должна выбросить ValueError."""
    with pytest.raises(ValueError, match="LLM API keys not found"):
        APIKeyRotator(keys=[])


def test_rotator_ban_key():
    """Тест: мертвый ключ должен удаляться из ротации навсегда."""
    rotator = APIKeyRotator(keys=["key_1", "key_2"])
    assert rotator.total_keys() == 2

    rotator.ban_key("key_1")

    assert rotator.total_keys() == 1
    assert rotator.get_next_key() == "key_2"
    assert rotator.get_next_key() == "key_2"  # Остался только один


def test_rotator_cooldown_key():
    """Тест: Rate Limit должен временно убирать ключ из выдачи."""
    rotator = APIKeyRotator(keys=["key_1", "key_2"])

    # Отправляем первый ключ в долгий кулдаун
    rotator.cooldown_key("key_1", seconds=300)

    # Теперь ротатор должен возвращать только второй ключ, пропуская первый
    assert rotator.get_next_key() == "key_2"
    assert rotator.get_next_key() == "key_2"

    # Если отправим в кулдаун и второй ключ — должна быть выброшена ошибка
    rotator.cooldown_key("key_2", seconds=30)
    with pytest.raises(RuntimeError, match="Необходимо подождать"):
        rotator.get_next_key()
