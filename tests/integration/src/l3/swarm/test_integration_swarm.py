import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import SwarmConfig
from src.utils.token_tracker import TokenTracker
from src.l3_agent.swarm.spawn import SwarmManager
from src.l3_agent.swarm.skills.report import SubagentReport
from src.l3_agent.skills.registry import register_instance, clear_registry, skill, SkillResult
from src.l3_agent.swarm.roles import Subagents


@pytest.mark.asyncio
async def test_integration_swarm_full_cycle(tmp_path: Path):
    """
    Интеграционный тест: "Оркестратор -> Субагент -> Отчет -> EventBus -> Оркестратор".
    Проверяет, что запуск субагента реально приводит к выполнению ReAct-цикла,
    сохранению отчета на диск и публикации события в шину для главного агента.
    """
    clear_registry()

    # 1. ПОДГОТОВКА ИНФРАСТРУКТУРЫ
    bus = EventBus()

    # Мокаем обработчик шины, чтобы поймать событие
    bus_receiver = MagicMock()
    bus_receiver.__name__ = "mock_bus_receiver"  # Fix: EventBus логирует __name__
    bus.subscribe(Events.SUBAGENT_TASK_COMPLETED, bus_receiver)

    tracker = TokenTracker()
    sandbox_dir = tmp_path / "sandbox"

    # Регистрируем навык отправки отчетов
    report_skill = SubagentReport(event_bus=bus, sandbox_dir=sandbox_dir)
    register_instance(report_skill)

    # Регистрируем фиктивный навык для субагента,
    # чтобы SwarmManager при инициализации увидел, что роль CODER активна (RBAC)
    class DummySkill:
        @skill(swarm_roles=[Subagents.CODER])
        async def dummy_func(self) -> SkillResult:
            return SkillResult.ok("OK")

    register_instance(DummySkill())

    config = SwarmConfig(enabled=True, subagent_model="fast-model", max_concurrent_workers=1)

    # 2. МОКАЕМ ОТВЕТ LLM
    # Настраиваем LLM так, чтобы субагент сразу понял задачу и вернул tool_call для отчета
    mock_llm = MagicMock()
    mock_session = AsyncMock()

    mock_msg = MagicMock()
    mock_msg.content = None
    # ФИКС: LLM обязана вызывать `execute_skill` и передавать AgentResponse JSON (с мыслями и массивом действий)
    mock_msg.tool_calls = [
        MagicMock(
            function=MagicMock(
                name="execute_skill",
                arguments='{"thoughts": "Задача решена.", "actions":[{"tool_name": "SubagentReport.submit_final_report", "parameters": {"subagent_id": "test_123", "role": "coder", "report": "# Задача выполнена. Все баги починены."}}]}',
            )
        )
    ]

    # На втором шаге LLM возвращает пустой массив действий для завершения цикла
    mock_msg_exit = MagicMock()
    mock_msg_exit.content = '{"thoughts": "Завершаю работу.", "actions":[]}'
    mock_msg_exit.tool_calls = None

    mock_session.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=mock_msg)]),
        MagicMock(choices=[MagicMock(message=mock_msg_exit)]),
    ]
    mock_llm.get_session.return_value = mock_session

    # 3. ИНИЦИАЛИЗАЦИЯ SWARM MANAGER
    with patch("src.l3_agent.swarm.spawn.SwarmPromptBuilder") as mock_builder:
        mock_builder.return_value.build.return_value = "System Prompt"
        manager = SwarmManager(
            llm_client=mock_llm, swarm_config=config, root_dir=tmp_path, token_tracker=tracker
        )

    # 4. ЗАПУСК (Оркестратор спавнит рабочего)
    # Чтобы проконтролировать ID, мы замокаем uuid внутри spawn_subagent
    with patch("src.l3_agent.swarm.spawn.uuid.uuid4", return_value=MagicMock(hex="test_123")):
        res = await manager.spawn_subagent(role="coder", task_description="Почини мне код")

    assert res.is_success is True

    # Дожидаемся завершения фоновой задачи субагента
    for task in list(manager.active_tasks):
        await task

    # Даем шине событий время на обработку
    if bus.background_tasks:
        await asyncio.gather(*bus.background_tasks)

    # 5. ПРОВЕРКА РЕЗУЛЬТАТОВ
    # А. Проверяем, что отчет сохранен на диск физически
    report_file = sandbox_dir / "_system" / "subagents" / "coder_test_123.md"
    assert report_file.exists()
    assert "# Задача выполнена" in report_file.read_text(encoding="utf-8")

    # Б. Проверяем, что событие улетело в EventBus (и может разбудить главного агента)
    bus_receiver.assert_called_once()
    kwargs = bus_receiver.call_args[1]
    assert kwargs["subagent_id"] == "test_123"
    assert kwargs["role"] == "coder"
    assert "coder_test_123.md" in kwargs["message"]
