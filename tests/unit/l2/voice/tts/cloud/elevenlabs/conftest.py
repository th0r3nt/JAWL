import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.utils.settings import ElevenLabsConfig
from src.l2_interfaces.voice.tts.cloud.elevenlabs.state import CloudElevenLabsTTSState
from src.l2_interfaces.voice.tts.cloud.elevenlabs.voices import VoiceManager
from src.l2_interfaces.voice.tts.cloud.elevenlabs.client import CloudElevenLabsTTSClient
from src.l2_interfaces.host.os.client import HostOSClient


@pytest.fixture
def el_config():
    """Базовый конфиг ElevenLabs для тестов."""
    return ElevenLabsConfig(
        enabled=True,
        tts_model="eleven_test_v1",
        main_voice="voice_123",
        stability=0.4,
        similarity_boost=0.9,
    )


@pytest.fixture
def el_state():
    """Изолированный стейт с малым лимитом истории."""
    return CloudElevenLabsTTSState(history_limit=3)


@pytest.fixture
def el_voice_manager(el_config):
    return VoiceManager(el_config)


@pytest.fixture
def el_client(el_state, el_voice_manager):
    return CloudElevenLabsTTSClient(
        state=el_state,
        voice_manager=el_voice_manager,
        api_key="test_key",
        api_url="https://api.test.com/v1",
    )


@pytest.fixture
def mock_os_client(tmp_path):
    """Мок гейткипера ОС для перехвата сохранения файлов."""
    os_client = MagicMock(spec=HostOSClient)

    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    os_client.sandbox_dir = sandbox_dir

    def mock_validate(path, is_write=False):
        if "error" in str(path):
            raise PermissionError("SANDBOX: Доступ запрещен")
        return (sandbox_dir / Path(path).name).resolve()

    os_client.validate_path.side_effect = mock_validate
    return os_client
