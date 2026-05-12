"""
Фикстуры для юнит-тестов Cloud Whisper STT.

Изолируют состояние, конфигурацию и зависимости клиента.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.utils.settings import CloudWhisperConfig
from src.l2_interfaces.voice.stt.cloud.whisper.state import CloudWhisperSTTState
from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient
from src.l2_interfaces.host.os.client import HostOSClient


@pytest.fixture
def whisper_config() -> CloudWhisperConfig:
    """Базовый конфиг Whisper STT для тестов."""
    return CloudWhisperConfig(
        enabled=True,
        model="whisper-1",
        temperature=0.2,
        timeout_sec=60,
    )


@pytest.fixture
def whisper_state() -> CloudWhisperSTTState:
    """Изолированный стейт с малым лимитом истории."""
    return CloudWhisperSTTState(history_limit=3)


@pytest.fixture
def whisper_client(
    whisper_state: CloudWhisperSTTState, whisper_config: CloudWhisperConfig
) -> CloudWhisperSTTClient:
    """Клиент с фейковыми данными авторизации."""
    return CloudWhisperSTTClient(
        state=whisper_state,
        config=whisper_config,
        api_key="fake_api_key",
        api_url="http://fake.api.url",
    )


@pytest.fixture
def mock_os_client(tmp_path: Path) -> HostOSClient:
    """Мок гейткипера ОС для перехвата и проверки путей."""
    os_client = MagicMock(spec=HostOSClient)

    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    os_client.sandbox_dir = sandbox_dir

    def mock_validate(path: str, is_write: bool = False) -> Path:
        if "error" in str(path):
            raise PermissionError("SANDBOX: Доступ запрещен")
        return (sandbox_dir / Path(path).name).resolve()

    os_client.validate_path.side_effect = mock_validate
    return os_client
