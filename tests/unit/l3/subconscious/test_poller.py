import pytest
from src.l3_agent.subconscious.poller import SubconsciousPoller
from src.l3_agent.subconscious.schema import Pattern
from src.utils.event.registry import Events


@pytest.mark.asyncio
async def test_poller_increments_and_triggers(mock_subconscious_deps):
    """Тест: Поллер считает тики и отправляет триггеры при достижении лимита."""
    poller = SubconsciousPoller(
        agent_state=mock_subconscious_deps["agent_state"],
        event_bus=mock_subconscious_deps["event_bus"],
        config=mock_subconscious_deps["config"],
    )

    # 1 тик
    await poller.on_tick_saved()
    assert poller.counters[Pattern.CONSOLIDATION] == 1
    assert poller.counters[Pattern.REFLECTION] == 1
    mock_subconscious_deps["event_bus"].publish.assert_not_called()

    # 2 тик - Консолидация (лимит 2) должна выстрелить
    await poller.on_tick_saved()
    assert poller.counters[Pattern.CONSOLIDATION] == 0  # Сбросился
    assert poller.counters[Pattern.REFLECTION] == 2

    mock_subconscious_deps["event_bus"].publish.assert_called_once_with(
        Events.SUBCONSCIOUS_TRIGGERED, pattern=Pattern.CONSOLIDATION
    )

    # Проверяем, что стейт агента обновился для отображения в промпте
    assert (
        mock_subconscious_deps["agent_state"].subconscious_counters[
            Pattern.CONSOLIDATION.value
        ]["current"]
        == 0
    )
    assert (
        mock_subconscious_deps["agent_state"].subconscious_counters[
            Pattern.REFLECTION.value
        ]["current"]
        == 2
    )


@pytest.mark.asyncio
async def test_poller_disabled_config(mock_subconscious_deps):
    """Тест: Если подсознание выключено, поллер ничего не делает."""
    mock_subconscious_deps["config"].enabled = False
    poller = SubconsciousPoller(
        agent_state=mock_subconscious_deps["agent_state"],
        event_bus=mock_subconscious_deps["event_bus"],
        config=mock_subconscious_deps["config"],
    )

    await poller.on_tick_saved()
    assert poller.counters[Pattern.CONSOLIDATION] == 0
    mock_subconscious_deps["event_bus"].publish.assert_not_called()
