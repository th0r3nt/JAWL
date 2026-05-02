import pytest
from pathlib import Path

from src.l3_agent.skills.registry import execute_skill, clear_registry, register_instance
from src.l3_agent.skills.schema import ActionCall

from src.utils.settings import HostOSConfig
from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.skills.files.writer import HostOSWriter


@pytest.mark.asyncio
async def test_integration_llm_json_to_real_disk(tmp_path: Path):
    """
    Тест: "Мозг -> Руки".
    Проверяет, что Pydantic-схема корректно парсит ActionCall,
    передает его в реальный скилл, и тот вносит физические изменения на диск.
    """
    clear_registry()

    # 1. Поднимаем реальный клиент Host OS (направленный во временную папку)
    config = HostOSConfig(access_level=HostOSAccessLevel.SANDBOX)
    state = HostOSState()
    client = HostOSClient(base_dir=tmp_path, config=config, state=state, timezone=3)

    # 2. Регистрируем реальный навык
    writer = HostOSWriter(client)
    register_instance(writer)

    # 3. Эмулируем распарсенный ответ от LLM
    actions = [
        ActionCall(
            tool_name="HostOSWriter.write_file",
            parameters={
                "filepath": "integration_test.txt",
                "content": "Real data on real disk!",
            },
        )
    ]

    # 4. Прогоняем через ядро
    report = await execute_skill(actions)

    # 5. Проверяем результаты
    assert "успешно перезаписан" in report

    # Проверяем физический файл на диске
    target_file = tmp_path / "sandbox" / "integration_test.txt"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "Real data on real disk!"
