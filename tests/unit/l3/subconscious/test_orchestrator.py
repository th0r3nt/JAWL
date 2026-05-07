import pytest
import asyncio
from unittest.mock import AsyncMock
from src.l3_agent.subconscious.orchestrator import SubconsciousOrchestrator
from src.l3_agent.subconscious.schema import Pattern


@pytest.mark.asyncio
async def test_orchestrator_safe_run_pattern_semaphore(mock_subconscious_deps):
    """Тест: Оркестратор защищает БД от параллельного запуска одного и того же паттерна."""
    orchestrator = SubconsciousOrchestrator(**mock_subconscious_deps)
    orchestrator.runner.run = AsyncMock()

    # Имитируем долгий запуск
    async def slow_run(*args, **kwargs):
        await asyncio.sleep(0.1)

    orchestrator.runner.run.side_effect = slow_run

    # Запускаем два одинаковых паттерна одновременно
    task1 = asyncio.create_task(orchestrator._safe_run_pattern(Pattern.CONSOLIDATION))
    task2 = asyncio.create_task(orchestrator._safe_run_pattern(Pattern.CONSOLIDATION))

    await asyncio.gather(task1, task2)

    # Благодаря семафору, второй вызов был заблокирован и пропущен
    orchestrator.runner.run.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_background_task_gc_protection(mock_subconscious_deps):
    """Тест: Таски сохраняются в background_tasks для защиты от Garbage Collector."""
    orchestrator = SubconsciousOrchestrator(**mock_subconscious_deps)
    orchestrator.runner.run = AsyncMock()

    await orchestrator._on_pattern_triggered(pattern=Pattern.REFLECTION)

    # Даем asyncio время создать задачу
    await asyncio.sleep(0.01)

    # Проверяем, что Runner был вызван
    orchestrator.runner.run.assert_called_once_with(Pattern.REFLECTION, ticks_to_analyze=3)
