"""
Интеграционные тесты для конкурентности и семафоров подсистемы Swarm.
Гарантируют, что система не превысит лимиты Rate Limit провайдера LLM (HTTP 429).
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.utils.settings import SwarmConfig
from src.l3_agent.swarm.spawn import SwarmManager
from src.l3_agent.swarm.roles import Subagents


@pytest.fixture
def mock_registry_for_concurrency():
    """Мокает реестр, чтобы роли были активны."""
    return {
        "DummySkill": {"swarm_roles": [Subagents.CODER]},
    }


@pytest.mark.asyncio
async def test_integration_swarm_concurrency_semaphore(
    mock_registry_for_concurrency, tmp_path: Path
):
    """
    Интеграционный тест: "Оркестратор спавнит 5 агентов -> Семафор пускает только 2 одновременно".
    Доказывает, что параметр 'max_concurrent_workers' реально блокирует излишнюю
    нагрузку на сеть и API ключи языковых моделей.
    """

    # Устанавливаем жесткий лимит: не больше 2 субагентов одновременно
    config = SwarmConfig(enabled=True, subagent_model="test-model", max_concurrent_workers=2)

    with patch("src.l3_agent.swarm.spawn._REGISTRY", mock_registry_for_concurrency):
        with patch("src.l3_agent.swarm.spawn.SwarmPromptBuilder"):
            manager = SwarmManager(
                llm_client=MagicMock(),
                swarm_config=config,
                root_dir=tmp_path,
                token_tracker=MagicMock(),
            )

    # Переменные для отслеживания параллелизма
    active_runs = 0
    max_active_runs = 0
    lock = asyncio.Lock()

    # Подменяем реальный цикл субагента заглушкой, которая имитирует работу
    async def mock_loop_run(*args, **kwargs):
        nonlocal active_runs, max_active_runs

        async with lock:
            active_runs += 1
            if active_runs > max_active_runs:
                max_active_runs = active_runs

        # Имитируем тяжелую работу (запрос к LLM)
        await asyncio.sleep(0.1)

        async with lock:
            active_runs -= 1

    with patch("src.l3_agent.swarm.spawn.SubagentLoop.run", new=mock_loop_run):
        # Оркестратор жадно спавнит сразу 5 рабочих задач
        for i in range(5):
            res = await manager.spawn_subagent("coder", f"Task {i}")
            assert res.is_success is True

        # Ждем завершения всех запущенных asyncio-тасок
        for task in list(manager.active_tasks):
            await task

    # ГЛАВНАЯ ПРОВЕРКА: Несмотря на 5 спавнов, в любой момент времени
    # физически работало не более 2-х агентов
    assert max_active_runs == 2
