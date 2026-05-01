import pytest
from pathlib import Path
from src.utils.settings import HostOSConfig
from src.l0_state.interfaces.host.os_state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient


@pytest.fixture
def os_client(tmp_path: Path):
    """
    Создает изолированного клиента ПК с уровнем OBSERVER (1).
    Передает временную директорию tmp_path напрямую как корень фреймворка.
    """

    config = HostOSConfig(
        enabled=True,
        access_level=1,
        env_access=False,
        monitoring_interval_sec=20,
        execution_timeout_sec=60,
        file_read_max_chars=3000,
        file_list_limit=100,
        http_response_max_chars=1000,
        top_processes_limit=10,
    )
    state = HostOSState()
    client = HostOSClient(base_dir=tmp_path, config=config, state=state, timezone=3)
    return client
