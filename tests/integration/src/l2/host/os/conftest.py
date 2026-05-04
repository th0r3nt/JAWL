"""
Общие фикстуры для интеграционных тестов слоя Host OS.
Обеспечивают изолированное создание клиента гейткипера во временных папках.
"""

import pytest
from pathlib import Path

from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel


@pytest.fixture
def os_client(tmp_path: Path) -> HostOSClient:
    """
    Создает изолированного клиента ПК (Гейткипера) с уровнем OBSERVER (1).
    Передает временную директорию tmp_path от pytest напрямую как корень фреймворка,
    чтобы тесты не могли случайно удалить или изменить реальные файлы JAWL.
    """
    config = HostOSConfig(
        enabled=True,
        access_level=HostOSAccessLevel.OBSERVER.value,
        env_access=False,
        monitoring_interval_sec=20,
        execution_timeout_sec=60,
        file_read_max_chars=3000,
        file_list_limit=100,
        file_diff_max_chars=300,
        top_processes_limit=10,
    )

    state = HostOSState()

    # Инициализируем клиента
    client = HostOSClient(base_dir=tmp_path, config=config, state=state, timezone=3)

    return client
