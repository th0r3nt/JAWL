"""
End-to-End тест подсистемы Swarm (Делегирование) и Host OS.

Проверяет реальный Stateless-цикл субагента:
1. Запуск CODER субагента через SwarmManager.
2. Субагент читает файл в песочнице (HostOSReader).
3. Субагент изменяет файл (HostOSEditor).
4. Субагент сдает работу (SubagentReport).
5. Главный агент получает уведомление через EventBus.
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import SwarmConfig, HostOSConfig
from src.utils.token_tracker import TokenTracker

from src.l2_interfaces.host.os.state import HostOSState
from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.skills.files.reader import HostOSReader
from src.l2_interfaces.host.os.skills.files.editor import HostOSEditor

from src.l3_agent.llm.executor import LLMExecutor

from src.l3_agent.swarm.spawn import SwarmManager
from src.l3_agent.swarm.skills.report import SubagentReport
from src.l3_agent.skills.registry import register_instance, clear_registry


@pytest.mark.asyncio
async def test_e2e_swarm_refactoring_task(tmp_path: Path):
    """
    E2E Тест: Делегирование рефакторинга субагенту.
    """
    clear_registry()

    # 1. ПОДГОТОВКА ПЕСОЧНИЦЫ И ГЕЙТКИПЕРА
    os_config = HostOSConfig(access_level=HostOSAccessLevel.SANDBOX)
    os_state = HostOSState()
    os_client = HostOSClient(base_dir=tmp_path, config=os_config, state=os_state, timezone=3)

    target_file = os_client.sandbox_dir / "app.py"
    target_file.write_text("def hello():\n    return 'old_code'\n", encoding="utf-8")

    # 2. РЕГИСТРАЦИЯ НАВЫКОВ
    register_instance(HostOSReader(os_client))
    register_instance(HostOSEditor(os_client))

    bus = EventBus()
    # Мокаем получателя из шины, чтобы проверить, дошел ли ивент до ядра
    mock_bus_listener = MagicMock()
    mock_bus_listener.__name__ = "mock_listener"
    bus.subscribe(Events.SUBAGENT_TASK_COMPLETED, mock_bus_listener)

    register_instance(SubagentReport(event_bus=bus, sandbox_dir=os_client.sandbox_dir))

    # 3. НАСТРОЙКА SWARM
    swarm_config = SwarmConfig(
        enabled=True, subagent_model="test-model", max_concurrent_workers=1
    )
    tracker = TokenTracker()

    # 4. МОКАЕМ ОТВЕТЫ LLM (Имитируем шаги мыслительного процесса субагента)
    # Шаг 1: Агент просит прочитать файл
    msg_step_1 = MagicMock()
    msg_step_1.content = None
    msg_step_1.tool_calls = [
        MagicMock(
            function=MagicMock(
                name="execute_skill",
                arguments=json.dumps(
                    {
                        "thoughts": "Мне нужно прочитать файл, чтобы понять, что исправлять.",
                        "actions": [
                            {
                                "tool_name": "HostOSReader.read_file",
                                "parameters": {"filepath": "sandbox/app.py"},
                            }
                        ],
                    }
                ),
            )
        )
    ]

    # Шаг 2: Агент патчит файл
    msg_step_2 = MagicMock()
    msg_step_2.content = None
    msg_step_2.tool_calls = [
        MagicMock(
            function=MagicMock(
                name="execute_skill",
                arguments=json.dumps(
                    {
                        "thoughts": "Я вижу старый код. Меняю 'old_code' на 'new_code'.",
                        "actions": [
                            {
                                "tool_name": "HostOSEditor.patch_file",
                                "parameters": {
                                    "filepath": "sandbox/app.py",
                                    "search_block": "return 'old_code'",
                                    "replace_block": "return 'new_code'",
                                },
                            }
                        ],
                    }
                ),
            )
        )
    ]

    # Шаг 3: Агент сдает отчет
    msg_step_3 = MagicMock()
    msg_step_3.content = None
    msg_step_3.tool_calls = [
        MagicMock(
            function=MagicMock(
                name="execute_skill",
                arguments=json.dumps(
                    {
                        "thoughts": "Файл пропатчен. Сдаю работу.",
                        "actions": [
                            {
                                "tool_name": "SubagentReport.submit_final_report",
                                "parameters": {
                                    "subagent_id": "test_id",
                                    "role": "coder",
                                    "report": "Баг исправлен.",
                                },
                            }
                        ],
                    }
                ),
            )
        )
    ]

    # Шаг 4: Агент завершает работу (возвращает empty actions list actions)
    msg_step_4 = MagicMock()
    msg_step_4.content = None
    msg_step_4.tool_calls = [
        MagicMock(
            function=MagicMock(
                name="execute_skill",
                arguments=json.dumps({"reflection": "Выхожу.", "actions": []}),
            )
        )
    ]

    mock_llm = MagicMock()
    mock_session = AsyncMock()
    mock_session.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=msg_step_1)]),
        MagicMock(choices=[MagicMock(message=msg_step_2)]),
        MagicMock(choices=[MagicMock(message=msg_step_3)]),
        MagicMock(choices=[MagicMock(message=msg_step_4)]),
    ]
    mock_llm.get_session.return_value = mock_session

    # ==========================
    # ВЫПОЛНЕНИЕ
    # ==========================

    llm_executor = LLMExecutor(mock_llm, tracker)

    with patch("src.l3_agent.swarm.spawn.SwarmPromptBuilder") as mock_builder:
        mock_builder.return_value.build.return_value = "System Prompt"
        manager = SwarmManager(
            executor=llm_executor,
            swarm_config=swarm_config,
            root_dir=tmp_path,
        )

    # Фиксируем ID для теста
    with patch("src.l3_agent.swarm.spawn.uuid.uuid4", return_value=MagicMock(hex="test_id")):
        res = await manager.spawn_subagent(
            role="coder", task_description="Замени old_code на new_code в app.py"
        )

    assert res.is_success is True

    # Ждем завершения таски субагента
    for task in list(manager.active_tasks):
        await task

    # Ждем EventBus
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # ==========================
    # ПРОВЕРКИ
    # ==========================

    # 1. Проверяем, что файл ФИЗИЧЕСКИ изменился на диске
    updated_code = target_file.read_text(encoding="utf-8")
    assert "return 'new_code'" in updated_code
    assert "return 'old_code'" not in updated_code

    # 2. Проверяем, что файл отчета ФИЗИЧЕСКИ сохранился
    report_file = os_client.sandbox_dir / "_system" / "subagents" / "coder_test_id.md"
    assert report_file.exists()
    assert "Баг исправлен" in report_file.read_text(encoding="utf-8")

    # 3. Проверяем, что Главный агент (Heartbeat) был разбужен событием SUBAGENT_TASK_COMPLETED
    mock_bus_listener.assert_called_once()
    kwargs = mock_bus_listener.call_args[1]
    assert kwargs["subagent_id"] == "test_id"
    assert kwargs["role"] == "coder"
    assert "completed the delegated task" in kwargs["message"]
