import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.utils.settings import EdgeConfig
from src.l2_interfaces.voice.tts.cloud.edge.state import CloudEdgeTTSState
from src.l2_interfaces.voice.tts.cloud.edge.voices import EdgeVoiceManager
from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient
from src.l2_interfaces.host.os.client import HostOSClient


@pytest.fixture
def edge_config():
    """Базовый конфиг Edge TTS для тестов."""
    return EdgeConfig(
        enabled=True,
        main_voice="ru-RU-SvetlanaNeural",
        available_voices=[],
        rate="+10%",
        volume="-5%",
        pitch="+0Hz",
    )


@pytest.fixture
def edge_state():
    """Изолированный стейт с малым лимитом истории."""
    return CloudEdgeTTSState(history_limit=3)


@pytest.fixture
def edge_voice_manager(edge_config):
    return EdgeVoiceManager(edge_config)


@pytest.fixture
def edge_client(edge_state, edge_voice_manager):
    return EdgeClient(
        state=edge_state,
        voice_manager=edge_voice_manager,
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
