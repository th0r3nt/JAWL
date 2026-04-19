import pytest
from unittest.mock import AsyncMock
from src.l3_agent.context.builder import ContextBuilder
from src.l0_state.agent.state import AgentState


@pytest.mark.asyncio
async def test_context_builder_build():
    """Тест: ContextBuilder успешно делегирует сборку реестру."""
    agent_state = AgentState()
    agent_state.llm_model = "test-model"

    # Мокаем Registry
    mock_registry = AsyncMock()
    # Имитируем, что разные провайдеры вернули свои блоки
    mock_registry.gather_all.return_value = "### TELETHON [ON]\nAccount info..."

    builder = ContextBuilder(agent_state=agent_state, registry=mock_registry)

    payload = {"chat_id": 123, "text": "Hello Agent"}
    context = await builder.build(event_name="TEST_EVENT", payload=payload, missed_events=[])

    # Проверяем, что реестр был вызван с нужными параметрами
    mock_registry.gather_all.assert_awaited_once_with(
        event_name="TEST_EVENT", payload=payload, missed_events=[]
    )

    # Проверяем, что в итоговом тексте есть куски от всех систем
    assert "## SKILLS" in context
    assert "### TELETHON [ON]" in context
    assert "## HEARTBEAT" in context
    assert "TEST_EVENT" in context
    assert "text: Hello Agent" in context
