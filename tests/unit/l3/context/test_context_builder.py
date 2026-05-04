import pytest
from src.l3_agent.context.builder import ContextBuilder
from src.l0_state.agent.state import AgentState
from src.l3_agent.context.registry import ContextRegistry, ContextSection


@pytest.mark.asyncio
async def test_context_builder_build():
    """Тест: ContextBuilder успешно делегирует сборку реестру и склеивает результаты."""
    agent_state = AgentState()
    agent_state.llm_model = "test-model"

    registry = ContextRegistry()

    # Добавляем фейковый провайдер, как это делают интерфейсы
    async def fake_telethon(**kwargs):
        return "### TELETHON [ON]\nAccount info..."

    registry.register_provider("telethon", fake_telethon, section=ContextSection.INTERFACES)

    builder = ContextBuilder(agent_state=agent_state, registry=registry)

    payload = {"chat_id": 123, "text": "Hello Agent"}
    context = await builder.build(event_name="TEST_EVENT", payload=payload, missed_events=[])

    # Проверяем, что в итоговом тексте есть куски от всех систем
    assert "## SKILLS" in context
    assert "### TELETHON [ON]" in context
    assert "## EVENT LOG" in context
    assert "## CURRENT TRIGGER" in context
    assert "TEST_EVENT" in context
    assert "text: Hello Agent" in context


@pytest.mark.asyncio
async def test_context_registry_resilience():
    """Тест: Если один провайдер падает, реестр игнорирует его и отдает остальные."""
    registry = ContextRegistry()
    agent_state = AgentState()

    async def success_provider(**kwargs):
        return "Успешный блок"

    async def failing_provider(**kwargs):
        raise ValueError("Критическая ошибка БД/Сети")

    registry.register_provider("good", success_provider, section=ContextSection.DRIVES)
    registry.register_provider("bad", failing_provider, section=ContextSection.SKILLS)

    results = await registry.gather_all("EVENT", {}, [], agent_state=agent_state)

    # Реестр должен проглотить ошибку failing_provider и вернуть только good
    assert "good" in results
    assert results["good"] == "Успешный блок"
    assert "bad" not in results

def test_context_builder_format_single_event_proactive():
    """Тест: Сборщик контекста подставляет проактивный промпт только если включен тумблер."""
    agent_state = AgentState()
    builder = ContextBuilder(agent_state, ContextRegistry())

    # Proactive OFF (по умолчанию)
    agent_state.proactive_guidance = False
    res_off = builder._format_single_event("HEARTBEAT", {})
    assert "Рекомендуется проактивное выполнение действий" not in res_off

    # Proactive ON
    agent_state.proactive_guidance = True
    res_on = builder._format_single_event("HEARTBEAT", {})
    assert "Рекомендуется проактивное выполнение действий" in res_on
    assert "Векторы активности могут включать" in res_on