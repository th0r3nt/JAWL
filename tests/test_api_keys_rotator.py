import os
import pytest
from src.l3_agent.llm.api_keys.rotator import APIKeyRotator


# ===================================================================
# TESTS
# ===================================================================


def test_rotator_loads_and_sorts_keys(monkeypatch):
    """Тест: ключи успешно загружаются и сортируются по имени переменной."""
    # Очищаем старые ключи и задаем тестовые вразброс
    monkeypatch.delenv("LLM_API_KEY_1", raising=False)
    monkeypatch.setenv("LLM_API_KEY_3", "key_3")
    monkeypatch.setenv("LLM_API_KEY_1", "key_1")
    monkeypatch.setenv("LLM_API_KEY_2", "key_2")

    rotator = APIKeyRotator()

    assert rotator.total_keys() == 3
    # Проверяем, что первый ключ — именно key_1 (поскольку ключи сортируются)
    assert rotator.keys[0] == "key_1"
    assert rotator.keys[2] == "key_3"


def test_rotator_round_robin(monkeypatch):
    """Тест: ключи выдаются по кругу."""
    monkeypatch.setenv("LLM_API_KEY_1", "key_1")
    monkeypatch.setenv("LLM_API_KEY_2", "key_2")

    rotator = APIKeyRotator()

    # Первый круг
    assert rotator.get_next_key() == "key_1"
    assert rotator.get_next_key() == "key_2"

    # Второй круг (вернулись к началу)
    assert rotator.get_next_key() == "key_1"
    assert rotator.get_next_key() == "key_2"


def test_rotator_empty_env_raises_error(monkeypatch):
    """Тест: если ключей в .env нет, система должна выбросить ValueError."""
    # Очищаем всё, что начинается с LLM_API_KEY_
    for key in list(os.environ.keys()):
        if key.startswith("LLM_API_KEY_"):
            monkeypatch.delenv(key)

    # Проверяем, что бросается именно ValueError
    with pytest.raises(ValueError, match="LLM API keys not found"):
        APIKeyRotator()


def test_rotator_skips_empty_keys(monkeypatch):
    """Тест: пустые или состоящие из пробелов ключи должны игнорироваться."""
    monkeypatch.setenv("LLM_API_KEY_1", "key_1")
    monkeypatch.setenv("LLM_API_KEY_2", "   ")  # Пустой ключ из пробелов
    monkeypatch.setenv("LLM_API_KEY_3", "")  # Просто пустой ключ

    rotator = APIKeyRotator()

    # Должен остаться только один валидный ключ
    assert rotator.total_keys() == 1
    assert rotator.get_next_key() == "key_1"


def test_rotator_ban_key(monkeypatch):
    """Тест: мертвый ключ должен удаляться из ротации навсегда."""
    monkeypatch.setenv("LLM_API_KEY_1", "key_1")
    monkeypatch.setenv("LLM_API_KEY_2", "key_2")

    rotator = APIKeyRotator()
    assert rotator.total_keys() == 2

    rotator.ban_key("key_1")

    assert rotator.total_keys() == 1
    assert rotator.get_next_key() == "key_2"
    assert rotator.get_next_key() == "key_2"  # Остался только один


def test_rotator_cooldown_key(monkeypatch):
    """Тест: Rate Limit должен временно убирать ключ из выдачи."""
    monkeypatch.setenv("LLM_API_KEY_1", "key_1")
    monkeypatch.setenv("LLM_API_KEY_2", "key_2")

    rotator = APIKeyRotator()

    # Отправляем первый ключ в долгий кулдаун
    rotator.cooldown_key("key_1", seconds=300)

    # Теперь ротатор должен возвращать только второй ключ, пропуская первый
    assert rotator.get_next_key() == "key_2"
    assert rotator.get_next_key() == "key_2"

    # Если отправим в кулдаун и второй ключ — должна быть выброшена ошибка с просьбой подождать
    rotator.cooldown_key("key_2", seconds=30)
    with pytest.raises(RuntimeError, match="Необходимо подождать"):
        rotator.get_next_key()
