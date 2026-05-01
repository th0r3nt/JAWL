import pytest
from src.l0_state.interfaces.telegram.aiogram_state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient


def test_client_missing_token():
    """Тест: клиент не должен инициализироваться без токена."""
    state = AiogramState()
    with pytest.raises(ValueError, match="необходим bot_token"):
        AiogramClient(bot_token="", state=state)
